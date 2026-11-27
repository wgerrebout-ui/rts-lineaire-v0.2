"""Le Chemin des Rois - moteur de jeu (Python pur, sans Kivy, testable par simulation).

Le champ de bataille est un couloir (axe x). Equipe 0 a gauche (joueur), equipe 1 a droite.
L'interface (main.py) ne fait que lire l'etat du moteur et lui envoyer des ordres.
"""
import copy
import random
from bisect import bisect_left

VERSION = '0.2'

STEP = 1.0 / 30            # pas de simulation (s)
LENGTH = 2400.0            # longueur du couloir
BASE_X = (100.0, LENGTH - 100.0)
BASE_R = 60.0              # demi-largeur d'une base
BASE_HP = 4000.0
BASE_ARMOR = 2
BASE_DMG_MULT = 2.0        # les bases encaissent mal : une poussée réussie doit conclure la partie
BASE_RNG = 210.0           # portee du tir de defense de la base
BASE_DMG = 16.0
POP_MAX = 30               # unites par camp (hors heros)
LANES = 5                  # files paralleles (purement spatial : evite l'empilement)
GOLD_START = 220.0
INCOME = 14.0              # or par seconde
BOUNTY = 0.25              # part du cout recuperee par le camp qui tue
HERO_BOUNTY = 100
HERO_REVIVE_T = 12.0       # delai avant le retour du heros (s)
HERO_REVIVE_COST = 100     # or paye au retour
TIME_SCALE = 0.85          # rythme general du jeu (1.0 = vitesse d'origine)
HERO_AGGRO = 45.0          # les ennemis preferent une unite proche au heros (celui-ci ne doit pas tout encaisser)
DEPTH_K = 6.0              # cout de portee par file d'ecart en profondeur (concerne les heros)
HERO_YMAX = 2.6            # profondeur maximale du heros (en files, de -2.6 a +2.6)
HERO_VY = 3.0              # vitesse de deplacement en profondeur (files / s)
SUDDEN_T = 720.0           # apres 12 min, les deux bases s'affaiblissent (evite les parties sans fin)
HERO_MAXLV = 10
XP_TOTAL = (0, 60, 140, 240, 360, 500, 660, 840, 1040, 1260)   # experience totale pour etre niveau 1..10
XP_UNIT = {'soldier': 10, 'archer': 10, 'knight': 18, 'heavy': 25}
XP_HERO = 100              # experience gagnee en tuant le heros adverse
XP_RANGE = 450.0           # un ennemi qui meurt a moins de cette distance du heros lui rapporte de l'experience
HERO_HP_LVL = 0.08         # +8 % de vie par niveau
HERO_DMG_LVL = 0.06        # +6 % de degats par niveau
ULT_LEVEL = 6              # niveau de heros requis pour l'ultime
RALLY = 380.0              # distance a la base ou l'armee tient sa position
QUEUE_MAX = 6
DMG_SCALE = 0.55           # ralentit les combats (les armees s'accumulent au lieu de se renouveler au compte-gouttes)

STANCES = ('hold', 'advance', 'retreat', 'follow')
STANCE_NAMES = {'hold': 'Tenir', 'advance': 'Avancer', 'retreat': 'Retraite', 'follow': 'Suivre'}
KINDS = ('soldier', 'archer', 'knight', 'heavy')

# --------------------------------------------------------------------------- caracteristiques
# Reprises du RTS ; cout converti en or (bois + minerai), temps de fabrication divise par 4.
UNITS = {
    'soldier': dict(label='Soldat', hp=110, speed=78, dmg=12, rng=24, cd=0.9, cost=75, time=2.0, r=13, armor=2),
    'archer': dict(label='Archer', hp=50, speed=85, dmg=9, rng=140, cd=1.1, cost=80, time=2.0, r=11, armor=0),
    'knight': dict(label='Cavalier', hp=120, speed=135, dmg=16, rng=26, cd=1.0, cost=140, time=3.0, r=16, armor=1),
    'heavy': dict(label='Unité lourde', hp=240, speed=60, dmg=30, rng=32, cd=1.5, cost=180, time=4.0, r=19, armor=3),
}
# bonus de degats (attaquant, cible)
BONUS = {('soldier', 'knight'): 1.5, ('knight', 'archer'): 1.6, ('archer', 'soldier'): 1.5,
         ('heavy', 'soldier'): 1.3, ('archer', 'heavy'): 1.4, ('knight', 'heavy'): 0.8}
BUILD_MULT = {'archer': 0.4, 'knight': 0.8, 'heavy': 2.0, 'hero': 0.8}

FACTIONS = {
    'kingdom': dict(name="Royaume d'Aurèle", short='Royaume',
                    units=dict(soldier='Fantassin', archer='Archer', knight='Chevalier', heavy='Catapulte')),
    'horde': dict(name='Horde de Gorak', short='Horde',
                  units=dict(soldier='Grunt', archer='Chasseur', knight='Chevaucheur de loup', heavy='Ogre')),
    'sylvan': dict(name="Sylve d'Elenwë", short='Sylve',
                   units=dict(soldier='Garde-lame', archer='Rôdeur', knight='Cavalier-cerf', heavy='Ent')),
}


def make_stats(fac):
    u = copy.deepcopy(UNITS)
    for k, v in FACTIONS[fac]['units'].items():
        u[k]['label'] = v
    if fac == 'kingdom':
        u['heavy'].update(hp=120, speed=52, dmg=34, rng=230, cd=2.6, armor=0, r=18, cost=220, bmult=2.5, splash=45)
    elif fac == 'horde':
        u['soldier'].update(hp=125, dmg=14, cost=65)
        u['knight'].update(speed=150, hp=110)
        u['archer'].update(hp=40, rng=120)
        u['heavy'].update(hp=260, dmg=32, cost=170)
    elif fac == 'sylvan':
        u['archer'].update(rng=170, dmg=11, cost=85)
        u['soldier'].update(hp=95)
        u['knight'].update(speed=145, dmg=14)
        u['heavy'].update(hp=290, speed=55, dmg=24, rng=34, cd=1.7, armor=4, regen=2.5, r=20)
    return u


# effets temporaires : multiplicateurs de degats (dmg), de vitesse d'attaque (aspd), de deplacement (speed)
BUFFS = {
    'valor1': dict(dmg=1.2), 'valor2': dict(dmg=1.3), 'valor3': dict(dmg=1.4),
    'warcry1': dict(aspd=1.25, speed=1.05), 'warcry2': dict(aspd=1.4, speed=1.1), 'warcry3': dict(aspd=1.55, speed=1.15),
    'rage1': dict(dmg=1.3, speed=1.15), 'rage2': dict(dmg=1.5, speed=1.25), 'rage3': dict(dmg=1.7, speed=1.35),
    'bless': dict(taken=0.55),
    'fury': dict(dmg=1.5, aspd=1.4, speed=1.15),
}

# Heros (un par faction pour le jalon 0.1 ; 3 emplacements de sorts + 1 ultime reserve pour la suite).
# 'lvl' = niveau requis (inutilise en 0.1 : tout est debloque), l'ultime viendra au jalon 0.2.
HEROES = {
    'kingdom': dict(
        name='Paladin', icon='knight', scale=1.45,
        hp=520, speed=112, dmg=26, rng=34, cd=0.9, armor=4, r=18,
        spells=[
            dict(kind='cleave', name='Coup sacré', short='Frappe', desc='Frappe puissante devant le héros : blesse tous les ennemis proches devant lui. +30 % de dégâts par niveau.', icon='i_amove', cd=6.0, maxlv=3, dmg=60, reach=105),
            dict(kind='valor', name='Vaillance', short='Vaillance', desc="L'armée proche inflige 20 / 30 / 40 % de dégâts en plus pendant 8 s (niveaux 1 / 2 / 3).", icon='ab_k', cd=15.0, maxlv=3, dur=8.0, radius=300),
            dict(kind='heal', name='Prière', short='Soin', desc='Soigne le héros et les alliés proches. +30 % de soin par niveau.', icon='ab_s', cd=20.0, maxlv=3, heal=55, hero_heal=100, radius=260),
        ],
        ultimate=dict(kind='bless', name='Bénédiction royale', short='Bénédiction', icon='em_kingdom', cd=60.0,
                      maxlv=1, dur=10.0, radius=380, heal=0.30,
                      desc="Soigne 30 % de la vie de l'armée proche et réduit de près de moitié les dégâts qu'elle subit pendant 10 s.")),
    'horde': dict(
        name='Berserker', icon='knight', scale=1.45,
        hp=600, speed=118, dmg=30, rng=34, cd=0.85, armor=2, r=18,
        spells=[
            dict(kind='whirl', name='Tourbillon', short='Tourbillon', desc='Frappe tous les ennemis autour du héros. +30 % de dégâts par niveau.', icon='i_amove', cd=7.0, maxlv=3, dmg=55, radius=105),
            dict(kind='warcry', name='Cri de guerre', short='Cri guerre', desc="L'armée proche attaque 25 / 40 / 55 % plus vite et avance un peu plus vite pendant 8 s.", icon='ab_h', cd=15.0, maxlv=3, dur=8.0, radius=300),
            dict(kind='rage', name='Rage', short='Rage', desc='Le héros inflige 30 / 50 / 70 % de dégâts en plus, avance plus vite pendant 8 s et récupère de la vie.', icon='i_star', cd=16.0, maxlv=3, dur=8.0, heal=50),
        ],
        ultimate=dict(kind='fury', name='Fureur de Gorak', short='Fureur', icon='em_horde', cd=60.0,
                      maxlv=1, dur=10.0, radius=380,
                      desc="L'armée proche inflige 50 % de dégâts en plus, attaque 40 % plus vite et avance 15 % plus vite pendant 10 s.")),
}


def hero_available(fac):
    return fac in HEROES


# --------------------------------------------------------------------------- entites
class Base:
    is_base = True
    hero = False
    kind = 'base'

    def __init__(self, team):
        self.team = team
        self.x = BASE_X[team]
        self.hp = self.maxhp = BASE_HP
        self.r = BASE_R
        self.armor = BASE_ARMOR
        self.cd_t = 0.0
        self.flash = 0.0
        self.atk_t = 0.0
        self.buff = {}
        self.killer = None
        self.y = 0.0


class Unit:
    is_base = False
    hero = False

    def __init__(self, uid, team, kind, st, x, lane):
        self.uid = uid
        self.team = team
        self.kind = kind
        self.st = st
        self.x = x
        self.lane = lane
        self.y = float(lane - 2)
        self.hp = self.maxhp = float(st['hp'])
        self.r = st['r']
        self.armor = st['armor']
        self.cd_t = 0.0
        self.buff = {}
        self.face = 1 if team == 0 else -1
        self.moving = False
        self.idx = 0
        self.flash = 0.0
        self.atk_t = 0.0
        self.killer = None


class Hero(Unit):
    hero = True

    def __init__(self, uid, team, fac):
        d = HEROES[fac]
        st = dict(label=d['name'], hp=d['hp'], speed=d['speed'], dmg=d['dmg'], rng=d['rng'], cd=d['cd'],
                  armor=d['armor'], r=d['r'], cost=0, time=0)
        Unit.__init__(self, uid, team, 'hero', st, BASE_X[team] + (1 if team == 0 else -1) * (BASE_R + 70), 2)
        self.fac = fac
        self.name = d['name']
        self.icon_kind = d['icon']
        self.scale = d['scale']
        self.base_hp = float(d['hp'])
        self.base_dmg = float(d['dmg'])
        self.level = 1
        self.xp = 0
        self.points = 1
        self.spells = ([dict(s, cdt=0.0, lv=0, ult=False) for s in d['spells']]
                       + [dict(d['ultimate'], cdt=0.0, lv=0, ult=True)])
        self.dead = False
        self.dead_t = 0.0
        self.inp_move = 0.0
        self.inp_atk = False
        self.inp_my = 0.0
        self.fleeing = False
        self.y = 0.0


def hero_xp_frac(h):
    if h.level >= HERO_MAXLV:
        return 1.0
    a, b = XP_TOTAL[h.level - 1], XP_TOTAL[h.level]
    return (h.xp - a) / float(b - a)


class Side:
    def __init__(self, team):
        self.team = team
        self.gold = GOLD_START
        self.queue = []
        self.prod_t = 0.0
        self.stance = 'advance'


def mult(e, key):
    m = 1.0
    for b in e.buff:
        m *= BUFFS[b].get(key, 1.0)
    return m


# --------------------------------------------------------------------------- partie
class Game:
    def __init__(self, fac0='kingdom', fac1='horde', diff=1, seed=None, ai0=False):
        if not (hero_available(fac0) and hero_available(fac1)):
            raise ValueError('héros indisponible pour cette faction')
        self.rng = random.Random(seed)
        self.facs = (fac0, fac1)
        self.stats = (make_stats(fac0), make_stats(fac1))
        self.bases = (Base(0), Base(1))
        self.side = [Side(0), Side(1)]
        self.units = []
        self.uid = 0
        self.heroes = [Hero(self._nid(), 0, fac0), Hero(self._nid(), 1, fac1)]
        self.hero_ai = [bool(ai0), True]
        self.income_mult = ((1.3, 0.5), (1.0, 0.85), (1.0, 1.15))[diff]
        self.xp_mult = ((1.0, 0.5), (1.0, 0.75), (1.0, 1.0))[diff]      # l'heros adverse monte moins vite en Facile
        self.ai = [AI(self, 0, diff) if ai0 else None, AI(self, 1, diff)]
        self.fx = []
        self.time = 0.0
        self.acc = 0.0
        self.winner = None
        self._ents = [[], []]
        self._xs = [[], []]
        self.kills = [0, 0]
        p = (0.6, 0.85, 1.0)[diff]                      # puissance du heros adverse
        h1 = self.heroes[1]
        h1.base_hp *= p
        h1.base_dmg *= p
        h1.maxhp = h1.hp = h1.base_hp
        h1.st['dmg'] = h1.base_dmg
        self.side[1].gold = (110.0, 190.0, 250.0)[diff]
        if diff == 0:
            self.bases[1].hp = self.bases[1].maxhp = 3000.0

    def _nid(self):
        self.uid += 1
        return self.uid

    # ------------------------------------------------------------------ ordres (appeles par l'interface)
    def pop(self, t):
        return sum(1 for u in self.units if u.team == t) + len(self.side[t].queue)

    def queue_unit(self, t, kind, n=1):
        """Met n unites en file (autant que l'or et la population le permettent). Retourne le nombre mis en file."""
        s = self.side[t]
        cost = self.stats[t][kind]['cost']
        done = 0
        for _ in range(n):
            if (self.winner is not None or len(s.queue) >= QUEUE_MAX or s.gold < cost
                    or self.pop(t) >= POP_MAX):
                break
            s.gold -= cost
            s.queue.append(kind)
            done += 1
        return done

    def set_stance(self, t, stance):
        if stance in STANCES:
            self.side[t].stance = stance

    def set_input(self, t, move, attack, my=0.0):
        h = self.heroes[t]
        h.inp_my = max(-1.0, min(1.0, my))
        h.inp_move = max(-1.0, min(1.0, move))
        h.inp_atk = bool(attack)

    def can_learn(self, t, idx):
        h = self.heroes[t]
        if idx >= len(h.spells):
            return False
        sp = h.spells[idx]
        need = ULT_LEVEL if sp['ult'] else 2 * sp['lv'] + 1
        return h.points > 0 and sp['lv'] < sp['maxlv'] and h.level >= need

    def learn(self, t, idx):
        if not self.can_learn(t, idx):
            return False
        h = self.heroes[t]
        h.spells[idx]['lv'] += 1
        h.points -= 1
        self.fx.append(('snd', 'sfx_click'))
        return True

    def _auto_learn(self, h):
        while h.points > 0:
            opts = [i for i in range(len(h.spells)) if self.can_learn(h.team, i)]
            if not opts:
                return
            ult = [i for i in opts if h.spells[i]['ult']]
            self.learn(h.team, ult[0] if ult else min(opts, key=lambda i: (h.spells[i]['lv'], i)))

    def _apply_level(self, h):
        lv = h.level
        new_max = h.base_hp * (1 + HERO_HP_LVL * (lv - 1))
        delta = new_max - h.maxhp
        h.maxhp = new_max
        h.st['dmg'] = h.base_dmg * (1 + HERO_DMG_LVL * (lv - 1))
        if not h.dead:
            h.hp = min(h.maxhp, h.hp + max(0.0, delta) + 0.15 * h.maxhp)

    def _give_xp(self, t, x, amount):
        h = self.heroes[t]
        if h.dead or abs(h.x - x) > XP_RANGE:
            return
        h.xp += amount * self.xp_mult[t]
        while h.level < HERO_MAXLV and h.xp >= XP_TOTAL[h.level]:
            h.level += 1
            h.points += 1
            self._apply_level(h)
            self.fx.append(('cast', h.x, 'Niveau %d !' % h.level, t))
            self.fx.append(('ring', h.x, 90, t, 'heal'))
            self.fx.append(('snd', 'sfx_ability'))

    def _buff(self, a, kind, lv, dur):
        for q in (1, 2, 3):
            a.buff.pop('%s%d' % (kind, q), None)
        a.buff['%s%d' % (kind, lv)] = dur

    def cast(self, t, idx):
        h = self.heroes[t]
        if self.winner is not None or h.dead or idx >= len(h.spells):
            return False
        sp = h.spells[idx]
        if sp['lv'] <= 0 or sp['cdt'] > 0:
            return False
        lv = sp['lv']
        f = 1.0 + 0.3 * (lv - 1)
        k = sp['kind']
        dr = h.face
        foes = self._foes(h)
        if k == 'cleave':
            dm = sp['dmg'] * f * mult(h, 'dmg')
            for o in foes:
                if -20 <= (o.x - h.x) * dr <= sp['reach'] + o.r:
                    self._hurt(o, dm, t, armor=False)
            self.fx.append(('ring', h.x + dr * sp['reach'] * 0.5, sp['reach'] * 0.6, t, 'hit'))
        elif k == 'whirl':
            dm = sp['dmg'] * f * mult(h, 'dmg')
            for o in foes:
                if abs(o.x - h.x) <= sp['radius'] + o.r:
                    self._hurt(o, dm, t, armor=False)
            self.fx.append(('ring', h.x, sp['radius'], t, 'hit'))
        elif k in ('valor', 'warcry'):
            for a in self._allies(h):
                if abs(a.x - h.x) <= sp['radius']:
                    self._buff(a, k, lv, sp['dur'])
            self.fx.append(('ring', h.x, sp['radius'], t, 'buff'))
        elif k == 'heal':
            for a in self._allies(h):
                if abs(a.x - h.x) <= sp['radius']:
                    a.hp = min(a.maxhp, a.hp + (sp['hero_heal'] if a.hero else sp['heal']) * f)
            self.fx.append(('ring', h.x, sp['radius'], t, 'heal'))
            self.fx.append(('snd', 'sfx_heal'))
        elif k == 'rage':
            self._buff(h, 'rage', lv, sp['dur'])
            h.hp = min(h.maxhp, h.hp + sp['heal'] * f)
            self.fx.append(('ring', h.x, 60, t, 'buff'))
        elif k == 'bless':
            for a in self._allies(h):
                if abs(a.x - h.x) <= sp['radius']:
                    a.hp = min(a.maxhp, a.hp + a.maxhp * sp['heal'])
                    a.buff['bless'] = sp['dur']
            self.fx.append(('ring', h.x, sp['radius'], t, 'heal'))
            self.fx.append(('snd', 'sfx_heal'))
        elif k == 'fury':
            for a in self._allies(h):
                if abs(a.x - h.x) <= sp['radius']:
                    a.buff['fury'] = sp['dur']
            self.fx.append(('ring', h.x, sp['radius'], t, 'buff'))
        sp['cdt'] = sp['cd']
        self.fx.append(('cast', h.x, sp['name'], t))
        self.fx.append(('snd', 'sfx_ability'))
        return True

    # ------------------------------------------------------------------ boucle
    def update(self, dt):
        if self.winner is not None:
            return
        self.acc += min(dt, 0.25) * TIME_SCALE
        n = 0
        while self.acc >= STEP and n < 8:
            self.acc -= STEP
            n += 1
            self._step(STEP)
            if self.winner is not None:
                break

    def pop_fx(self):
        f, self.fx = self.fx, []
        return f

    def _step(self, dt):
        self.time += dt
        for t in (0, 1):
            self.side[t].gold += INCOME * self.income_mult[t] * dt
            self._produce(t, dt)
        self._index()
        for ai in self.ai:
            if ai:
                ai.update(dt)
        for u in list(self.units):
            if u.hp > 0:
                self._act_unit(u, dt)
        for h in self.heroes:
            self._act_hero(h, dt)
        for b in self.bases:
            self._act_base(b, dt)
        if self.time > SUDDEN_T:
            wear = (2.0 + (self.time - SUDDEN_T) / 60.0 * 2.0) * dt
            for b in self.bases:
                b.hp -= wear
        self._cleanup()

    # ------------------------------------------------------------------ production
    def _produce(self, t, dt):
        s = self.side[t]
        if not s.queue:
            s.prod_t = 0.0
            return
        kind = s.queue[0]
        s.prod_t += dt
        if s.prod_t >= self.stats[t][kind]['time']:
            s.prod_t = 0.0
            s.queue.pop(0)
            dr = 1 if t == 0 else -1
            uid = self._nid()
            x = BASE_X[t] + dr * (BASE_R + 25) + self.rng.uniform(-3, 3)
            self.units.append(Unit(uid, t, kind, self.stats[t][kind], x, uid % LANES))
            self.fx.append(('snd', 'sfx_build') if t == 0 else ('none',))

    # ------------------------------------------------------------------ index spatial
    def _index(self):
        for t in (0, 1):
            ents = [u for u in self.units if u.team == t and u.hp > 0]
            h = self.heroes[t]
            if not h.dead and h.hp > 0:
                ents.append(h)
            ents.sort(key=lambda e: e.x)
            self._ents[t] = ents
            self._xs[t] = [e.x for e in ents]
            for i, e in enumerate(ents):
                e.idx = i

    def _nearest(self, e):
        """Cible la plus interessante (unite, heros ou base) et sa distance reelle de bord a bord.
        Pour les unites, le heros adverse compte comme plus loin qu'il n'est (HERO_AGGRO) : une unite
        presque aussi proche attire donc l'attention en premier."""
        t = 1 - e.team
        best = self.bases[t]
        bd = abs(best.x - e.x) - best.r - e.r
        bs = bd
        ents = self._ents[t]
        if ents:
            i = bisect_left(self._xs[t], e.x)
            w = 4 if e.hero else 2
            for j in range(max(0, i - w), min(len(ents), i + w)):
                o = ents[j]
                if o.hp <= 0:
                    continue
                d = abs(o.x - e.x) - o.r - e.r
                if o.hero or e.hero:
                    d += abs(o.y - e.y) * DEPTH_K
                sc = d + (HERO_AGGRO if (o.hero and not e.hero) else 0.0)
                if sc < bs:
                    best, bd, bs = o, d, sc
        return best, bd

    def _foes(self, e):
        return [o for o in self._ents[1 - e.team] if o.hp > 0]

    def _allies(self, e):
        return [o for o in self._ents[e.team] if o.hp > 0]

    def _blocked(self, u, dr):
        L = self._ents[u.team]
        j = u.idx + dr
        n = 0
        while 0 <= j < len(L) and n < 8:
            a = L[j]
            j += dr
            n += 1
            if a is u or a.hero or a.hp <= 0:
                continue
            gap = (a.x - u.x) * dr
            if gap < 0 or (gap == 0 and a.uid > u.uid):
                continue
            if gap > 40:
                break
            if a.lane == u.lane and gap < (a.r + u.r) * 0.9:
                return True
        return False

    # ------------------------------------------------------------------ combat
    def _hurt(self, target, dmg, team, armor=True, scale=1.0):
        if armor:
            dmg = max(1.0, dmg - target.armor)
        dmg *= scale * mult(target, 'taken')
        target.hp -= dmg
        target.flash = 0.12
        target.killer = team

    def _attack(self, a, tgt):
        st = a.st
        a.cd_t = st['cd'] / mult(a, 'aspd')
        a.atk_t = 0.18
        dm = st['dmg'] * mult(a, 'dmg')
        if tgt.is_base:
            dm *= st.get('bmult', BUILD_MULT.get(a.kind, 1.0)) * BASE_DMG_MULT
        else:
            dm *= BONUS.get((a.kind, tgt.kind), 1.0)
        self._hurt(tgt, dm, a.team, scale=DMG_SCALE)
        if st['rng'] > 60:
            self.fx.append(('proj', a.x, tgt.x, a.team, a.kind))
            self.fx.append(('snd', 'sfx_arrow'))
        else:
            self.fx.append(('hit', tgt.x, a.team))
            self.fx.append(('snd', 'sfx_hit'))
        sp = st.get('splash')
        if sp and not tgt.is_base:
            for o in self._foes(a):
                if o is not tgt and abs(o.x - tgt.x) <= sp:
                    self._hurt(o, dm * 0.6, a.team, scale=DMG_SCALE)

    def _tick(self, e, dt):
        e.cd_t -= dt
        if e.flash > 0:
            e.flash -= dt
        if e.atk_t > 0:
            e.atk_t -= dt
        if e.buff:
            for k in list(e.buff):
                e.buff[k] -= dt
                if e.buff[k] <= 0:
                    del e.buff[k]

    def _act_unit(self, u, dt):
        st = u.st
        t = u.team
        self._tick(u, dt)
        if st.get('regen'):
            u.hp = min(u.maxhp, u.hp + st['regen'] * dt)
        u.moving = False
        stance = self.side[t].stance
        dr = 1 if t == 0 else -1
        base_x = BASE_X[t]
        tgt, d = self._nearest(u)
        fight = True
        chase = False
        if stance == 'advance':
            want, chase = tgt.x, True
        elif stance == 'hold' or (stance == 'retreat' and abs(u.x - base_x) <= 200):
            rally = base_x + dr * (RALLY if stance == 'hold' else 110)
            if d <= 90:
                want, chase = tgt.x, True
            else:
                want = rally
        elif stance == 'retreat':
            want, fight = base_x + dr * 110, False
        else:  # follow
            h = self.heroes[t]
            if h.dead:
                want = base_x + dr * RALLY
            elif d <= 280 and abs(tgt.x - h.x) <= 450:
                want, chase = tgt.x, True
            elif u.kind == 'archer':
                want = h.x - dr * (45 + (u.uid % 5) * 20)
            else:                                   # corps a corps : en avant du heros, pour tenir la ligne
                want = h.x + dr * (45 + (u.uid % 5) * 20)
        if fight and d <= st['rng']:
            u.face = 1 if tgt.x >= u.x else -1
            if u.cd_t <= 0:
                self._attack(u, tgt)
            if chase:
                return
        dx = want - u.x
        if abs(dx) < 4:
            return
        mv = 1 if dx > 0 else -1
        if self._blocked(u, mv):
            return
        step = min(abs(dx), st['speed'] * mult(u, 'speed') * dt)
        u.x = max(20.0, min(LENGTH - 20.0, u.x + mv * step))
        if not (fight and d <= st['rng']):
            u.face = mv
        u.moving = True

    # ------------------------------------------------------------------ heros
    def _hero_move(self, h, mv, dt):
        tgt, d = self._nearest(h)
        if d <= 2 and (tgt.x - h.x) * mv > 0:
            return
        h.x = max(20.0, min(LENGTH - 20.0, h.x + mv * h.st['speed'] * mult(h, 'speed') * dt))
        h.face = mv
        h.moving = True

    def _act_hero(self, h, dt):
        for sp in h.spells:
            if sp['cdt'] > 0:
                sp['cdt'] -= dt
        t = h.team
        if h.dead:
            h.dead_t -= dt
            if h.dead_t <= 0:
                s = self.side[t]
                if s.gold >= HERO_REVIVE_COST:
                    s.gold -= HERO_REVIVE_COST
                    h.dead = False
                    h.hp = h.maxhp
                    h.buff = {}
                    h.x = BASE_X[t] + (1 if t == 0 else -1) * (BASE_R + 70)
                    self.fx.append(('ring', h.x, 70, t, 'heal'))
                else:
                    h.dead_t = 0.0
            return
        self._tick(h, dt)
        h.moving = False
        h.hp = min(h.maxhp, h.hp + (7.0 if abs(h.x - BASE_X[t]) < 220 else 1.2) * dt)
        tgt, d = self._nearest(h)
        if self.hero_ai[t]:
            self._auto_learn(h)
            self._hero_ai(h, tgt, d, dt)
        else:
            mv = h.inp_move
            if abs(h.inp_my) > 0.05:
                h.y = max(-HERO_YMAX, min(HERO_YMAX, h.y + h.inp_my * HERO_VY * dt))
                h.moving = True
            if abs(mv) > 0.05:
                self._hero_move(h, 1 if mv > 0 else -1, dt * abs(mv))
            if (h.inp_atk or abs(mv) <= 0.05) and d <= h.st['rng']:
                if abs(mv) <= 0.05:
                    h.face = 1 if tgt.x >= h.x else -1
                if h.cd_t <= 0:
                    self._attack(h, tgt)

    def _hero_ai(self, h, tgt, d, dt):
        t = h.team
        dr = 1 if t == 0 else -1
        rng = h.st['rng']
        if h.hp < h.maxhp * 0.3:
            h.fleeing = True
        elif h.hp > h.maxhp * 0.65:
            h.fleeing = False
        flee = h.fleeing and abs(h.x - BASE_X[t]) > 150
        if h.fleeing and not flee:
            pass
        elif flee:
            self._hero_move(h, -dr, dt)
        else:
            army = [e for e in self._ents[t] if not e.hero]
            if army:
                front = max(e.x for e in army) if t == 0 else min(e.x for e in army)
            else:
                front = BASE_X[t] + dr * 200
            if d <= rng:
                goal = None
            elif d <= 240 and not tgt.is_base:
                goal = tgt.x
            else:
                goal = front - dr * 40
            if goal is not None and abs(goal - h.x) > 10:
                self._hero_move(h, 1 if goal > h.x else -1, dt)
        goal_y = 0.0 if tgt.is_base else tgt.y
        h.y += max(-HERO_VY * dt, min(HERO_VY * dt, goal_y - h.y))
        if d <= rng:
            h.face = 1 if tgt.x >= h.x else -1
            if h.cd_t <= 0:
                self._attack(h, tgt)
        self._hero_spells(h)

    def _hero_spells(self, h):
        foes = self._foes(h)
        allies = self._allies(h)
        for i, sp in enumerate(h.spells):
            if sp['cdt'] > 0 or sp['lv'] <= 0:
                continue
            k = sp['kind']
            go = False
            if k == 'cleave':
                go = any(0 <= (o.x - h.x) * h.face <= sp['reach'] for o in foes)
            elif k == 'whirl':
                go = sum(1 for o in foes if abs(o.x - h.x) <= sp['radius']) >= 2
            elif k in ('valor', 'warcry'):
                go = (sum(1 for a in allies if abs(a.x - h.x) <= sp['radius']) >= 3
                      and sum(1 for o in foes if abs(o.x - h.x) <= 350) >= 2)
            elif k == 'heal':
                hurt = sum(1 for a in allies if abs(a.x - h.x) <= sp['radius'] and a.hp < a.maxhp * 0.6)
                go = hurt >= 2 or (h.hp < h.maxhp * 0.5 and any(abs(o.x - h.x) <= 200 for o in foes))
            elif k == 'rage':
                go = any(abs(o.x - h.x) <= 120 for o in foes)
            elif k in ('bless', 'fury'):
                near = sum(1 for a in allies if abs(a.x - h.x) <= sp['radius'])
                fo = sum(1 for o in foes if abs(o.x - h.x) <= 400)
                go = (near >= 4 and fo >= 3) or (k == 'bless' and h.hp < h.maxhp * 0.4 and fo >= 1)
            if go:
                self.cast(h.team, i)

    # ------------------------------------------------------------------ bases
    def _act_base(self, b, dt):
        self._tick(b, dt)
        if b.cd_t > 0:
            return
        tgt, d = self._nearest(b)
        if not tgt.is_base and d <= BASE_RNG:
            b.cd_t = 1.3
            self._hurt(tgt, BASE_DMG, b.team, scale=DMG_SCALE)
            self.fx.append(('proj', b.x, tgt.x, b.team, 'archer'))

    # ------------------------------------------------------------------ fin de pas
    def _cleanup(self):
        for u in self.units:
            if u.hp <= 0:
                self.fx.append(('death', u.x, u.team, u.kind))
                self.fx.append(('snd', 'sfx_death'))
                if u.killer is not None and u.killer != u.team:
                    self.side[u.killer].gold += u.st['cost'] * BOUNTY
                    self.kills[u.killer] += 1
                    self._give_xp(u.killer, u.x, XP_UNIT[u.kind])
        self.units = [u for u in self.units if u.hp > 0]
        for h in self.heroes:
            if h.hp <= 0 and not h.dead:
                h.dead = True
                h.dead_t = HERO_REVIVE_T
                h.hp = 0
                self.fx.append(('death', h.x, h.team, 'hero'))
                self.fx.append(('snd', 'sfx_death'))
                if h.killer is not None and h.killer != h.team:
                    self.side[h.killer].gold += HERO_BOUNTY
                    self._give_xp(h.killer, h.x, XP_HERO)
        for b in self.bases:
            if b.hp <= 0 and self.winner is None:
                self.winner = 1 - b.team
                self.fx.append(('end', self.winner))


# --------------------------------------------------------------------------- IA (adversaire, et joueur automatique pour les tests)
AI_THINK = (2.4, 1.3, 0.75)
AI_WAVE = (12, 8, 6)       # taille de l'armee adverse avant de partir a l'attaque


class AI:
    def __init__(self, game, team, diff=1):
        self.g = game
        self.t = team
        self.think = AI_THINK[diff]
        self.wave = AI_WAVE[diff]
        self.timer = 1.0
        self.diff = diff
        game.side[team].stance = 'hold'

    def update(self, dt):
        self.timer -= dt
        if self.timer > 0:
            return
        g, t = self.g, self.t
        self.timer = (0.7 + g.rng.random() * 0.6) * self.think
        s = g.side[t]
        mine = [u for u in g.units if u.team == t]
        enemy = [u for u in g.units if u.team != t]
        if len(s.queue) < 2 and g.pop(t) < POP_MAX:
            kind = self._pick(enemy)
            if s.gold >= g.stats[t][kind]['cost']:
                g.queue_unit(t, kind)
        n, m = len(mine), len(enemy)
        if s.stance == 'advance':
            if n <= 2 and m >= n + 5:
                s.stance = 'hold'
        elif n >= self.wave or (n >= self.wave - 3 and m <= n - 2):
            s.stance = 'advance'

    def _pick(self, enemy):
        g = self.g
        share = {k: 0.0 for k in KINDS}
        for u in enemy:
            share[u.kind] += 1.0 / max(1, len(enemy))
        base = {'soldier': 3.0, 'archer': 2.0, 'knight': 1.5, 'heavy': 1.0}
        w = {}
        for k in KINDS:
            adv = sum(share[e] * (BONUS.get((k, e), 1.0) - BONUS.get((e, k), 1.0)) for e in KINDS)
            w[k] = max(0.2, base[k] * (1.0 + adv * 1.5))
        r = g.rng.random() * sum(w.values())
        for k in KINDS:
            r -= w[k]
            if r <= 0:
                return k
        return 'soldier'
