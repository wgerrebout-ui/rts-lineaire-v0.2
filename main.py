"""Le Chemin des Rois - interface Kivy (jalon 0.1).

Tout est dessine directement avec des instructions graphiques (canvas), a partir de la taille de l'ecran.
Les touchers sont captes au niveau de la fenetre (Window.bind) pour que les boutons reagissent toujours.
Le moteur (corridor.py) ne depend pas de Kivy.
"""
import base64
import io
import math
import os
import time
import traceback

from kivy.app import App
from kivy.base import ExceptionHandler, ExceptionManager
from kivy.clock import Clock
from kivy.core.image import Image as CoreImage
from kivy.core.text import Label as CoreLabel
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle, Triangle
from kivy.graphics.texture import Texture
from kivy.metrics import dp
from kivy.uix.widget import Widget

import corridor as C
from assets_data import DATA
from sounds_data import SND

try:
    from kivy.core.audio import SoundLoader
except Exception:
    SoundLoader = None

APP = None
_ERR = set()
ERRS = []          # dernieres erreurs (affichees dans le journal du jeu)
VIEW_W = 900.0     # largeur du couloir visible a l'ecran (unites du moteur)
LANE_DY = 16.0     # decalage vertical entre files (dp)


# ------------------------------------------------------------------ journal d'erreurs
def log_error(tag='?'):
    try:
        msg = traceback.format_exc()
        key = (tag, msg[-160:])
        if key in _ERR or len(_ERR) > 60:
            return
        _ERR.add(key)
        line = '[%s] %s | %s' % (time.strftime('%d/%m %H:%M:%S'), tag, msg.strip().splitlines()[-1][:140])
        ERRS.append(line)
        del ERRS[:-12]
        base = APP.user_data_dir if APP else '.'
        with open(os.path.join(base, 'crash.log'), 'a') as f:
            f.write('[%s] %s\n%s\n' % (time.strftime('%d/%m %H:%M:%S'), tag, msg))
        if APP:
            APP.last_error = line
    except Exception:
        pass


class _Handler(ExceptionHandler):
    def handle_exception(self, inst):
        log_error('kivy')
        return ExceptionManager.PASS


# ------------------------------------------------------------------ textures et textes
_T = {}
_missing = set()


def blank_tex():
    t = Texture.create(size=(2, 2), colorfmt='rgba')
    t.blit_buffer(b'\x00' * 16, colorfmt='rgba', bufferfmt='ubyte')
    return t


def tex(name):
    t = _T.get(name)
    if t is None:
        try:
            t = CoreImage(io.BytesIO(base64.b64decode(DATA[name])), ext='png').texture
            t.mag_filter = 'linear'
            t.min_filter = 'linear'
        except Exception:
            if name not in _missing:
                _missing.add(name)
                log_error('texture ' + name)
            t = blank_tex()
        _T[name] = t
    return t


def hflip_coords(t):
    """Coordonnees de texture en miroir horizontal, valables quelle que soit l'orientation native de la texture."""
    c = t.tex_coords
    return (c[2], c[3], c[0], c[1], c[6], c[7], c[4], c[5])


_TXT = {}


def ctext(s, fs, col=(1, 1, 1, 1), bold=True, wrap=None, halign='center'):
    """Texture de texte avec contour (mise en cache)."""
    key = (s, round(fs, 1), col, bold, int(wrap) if wrap else 0, halign)
    t = _TXT.get(key)
    if t is None:
        kw = dict(text=s, font_size=fs, bold=bold, color=col, outline_width=max(1, int(dp(1))),
                  outline_color=(0, 0, 0, 1))
        if wrap:
            kw['text_size'] = (wrap, None)
            kw['halign'] = halign
        cl = CoreLabel(**kw)
        cl.refresh()
        t = cl.texture
        if len(_TXT) > 500:
            _TXT.clear()
        _TXT[key] = t
    return t


def text(s, x, y, fs, col=(1, 1, 1, 1), anchor='c', bold=True, wrap=None, halign='center'):
    """Dessine un texte centre sur (x, y) ; anchor : 'c' centre, 'l' bord gauche en x, 'r' bord droit en x."""
    t = ctext(s, fs, col, bold, wrap, halign)
    w, h = t.size
    px = x - w / 2 if anchor == 'c' else (x if anchor == 'l' else x - w)
    Color(1, 1, 1, 1)
    Rectangle(texture=t, pos=(px, y - h / 2), size=(w, h))
    return w, h


def pic(name, x, y, w, h, flip=False, col=(1, 1, 1, 1)):
    t = tex(name)
    Color(*col)
    if flip:
        Rectangle(texture=t, pos=(x, y), size=(w, h), tex_coords=hflip_coords(t))
    else:
        Rectangle(texture=t, pos=(x, y), size=(w, h))


def rrect(x, y, w, h, col, r=None):
    Color(*col)
    RoundedRectangle(pos=(x, y), size=(w, h), radius=[r if r is not None else dp(8)])


def bar(x, y, w, h, frac, col, bg=(0, 0, 0, 0.6)):
    Color(*bg)
    Rectangle(pos=(x, y), size=(w, h))
    frac = max(0.0, min(1.0, frac))
    if frac > 0:
        Color(*col)
        Rectangle(pos=(x, y), size=(w * frac, h))


# ------------------------------------------------------------------ sons
class Snd:
    def __init__(self, folder):
        self.dir = folder
        self.sound, self.music_on = True, True
        self.cache, self.last = {}, {}
        self.cur, self.cur_name = None, None
        try:
            os.makedirs(folder, exist_ok=True)
            for k, v in SND.items():
                p = os.path.join(folder, k + '.ogg')
                data = base64.b64decode(v)
                if not os.path.exists(p) or os.path.getsize(p) != len(data):
                    with open(p, 'wb') as f:
                        f.write(data)
        except Exception:
            log_error('sons')

    def get(self, name):
        if SoundLoader is None:
            return None
        s = self.cache.get(name)
        if s is None:
            try:
                s = SoundLoader.load(os.path.join(self.dir, name + '.ogg'))
            except Exception:
                s = None
            self.cache[name] = s
        return s

    def play(self, name, vol=0.7):
        if not self.sound:
            return
        now = time.time()
        if now - self.last.get(name, 0) < 0.09:
            return
        self.last[name] = now
        try:
            s = self.get(name)
            if s:
                s.volume = vol
                s.play()
        except Exception:
            log_error('play ' + name)

    def music(self, name, vol=0.45):
        try:
            if self.cur_name == name and self.cur and self.cur.state == 'play':
                return
            self.stop_music()
            self.cur_name = name
            if not self.music_on:
                return
            s = self.get(name)
            if s:
                s.loop = True
                s.volume = vol
                s.play()
                self.cur = s
        except Exception:
            log_error('musique ' + name)

    def stop_music(self):
        try:
            if self.cur:
                self.cur.stop()
        except Exception:
            pass
        self.cur, self.cur_name = None, None

    def toggle(self):
        on = not (self.sound or self.music_on)
        self.sound = self.music_on = on
        if on:
            self.cur_name = None
        else:
            self.stop_music()


# ------------------------------------------------------------------ vue principale
STANCE_ICON = {'hold': 'i_stop', 'advance': 'i_amove', 'retreat': 'i_home', 'follow': 'i_pop'}
PROJ = {'kingdom': 'arrow', 'horde': 'proj_bolt', 'sylvan': 'proj_orb'}
RING_COL = {'hit': (1.0, 0.55, 0.25), 'buff': (1.0, 0.9, 0.3), 'heal': (0.4, 1.0, 0.5)}
DIFF_NAMES = ('Facile', 'Normal', 'Difficile')
CREST = {'kingdom': 'ab_k', 'horde': 'ab_h', 'sylvan': 'ab_s'}


class GameView(Widget):
    def __init__(self, app, **kw):
        super().__init__(**kw)
        self.app = app
        self.state = 'menu'
        self.diff = 1
        self.g = None
        self.hit = []
        self.roles = {}
        self.stick = None
        self.move = 0.0
        self.my = 0.0
        self.atk = False
        self.hold = None
        self.fxs = []
        self.cam = 0.0
        self.t = 0.0
        self.end_t = 0.0
        self.game_t = 0.0
        self.dbg = 'aucun toucher reçu'
        self.tpos = {}
        Window.bind(on_touch_down=self.t_down, on_touch_move=self.t_move, on_touch_up=self.t_up,
                    on_keyboard=self.on_key)
        Clock.schedule_interval(self.frame, 1 / 30.)
        self.app.snd.music('music_menu', 0.4)

    # -------------------------------------------------------------- partie
    def start(self):
        self.g = C.Game('kingdom', 'horde', diff=self.diff)
        self.g.set_stance(0, 'follow')
        self.roles, self.stick, self.move, self.atk, self.hold = {}, None, 0.0, False, None
        self.fxs = []
        self.end_t = 0.0
        self.game_t = 0.0
        self.cam = self.g.heroes[0].x - VIEW_W * 0.3
        self.state = 'game'
        self.app.snd.music('music_battle', 0.4)

    def to_menu(self):
        self.state = 'menu'
        self.g = None
        self.roles, self.stick, self.move, self.atk, self.hold = {}, None, 0.0, False, None
        self.app.snd.music('music_menu', 0.4)

    # -------------------------------------------------------------- boucle
    def frame(self, dt):
        try:
            dt = min(dt, 0.1)
            self.t += dt
            if self.state == 'game' and self.g:
                self.update_game(dt)
            self.draw()
        except Exception:
            log_error('frame')

    def update_game(self, dt):
        g = self.g
        self.game_t += dt
        W = Window.width
        # appui long sur une carte : cinq unites d'un coup
        if self.hold:
            uid, kind, t0, done = self.hold
            if not done and self.t - t0 > 0.45:
                g.queue_unit(0, kind, 4)
                self.hold = (uid, kind, t0, True)
        if self.stick is None:
            self.my = 0.0
        g.set_input(0, self.move, self.atk, self.my)
        g.update(dt)
        for f in g.pop_fx():
            self.on_fx(f)
        h = g.heroes[0]
        target = h.x - VIEW_W / 2 + h.face * VIEW_W * 0.08
        target = max(-60.0, min(C.LENGTH - VIEW_W + 60.0, target))
        self.cam += (target - self.cam) * min(1.0, dt * 5.0)
        for f in self.fxs:
            f['age'] += dt
        self.fxs = [f for f in self.fxs if f['age'] < f['dur']][-140:]
        if g.winner is not None:
            self.end_t += dt
            if self.end_t > 1.6:
                self.state = 'end'
                self.roles, self.stick, self.move, self.atk = {}, None, 0.0, False
                self.app.snd.play('sfx_win' if g.winner == 0 else 'sfx_lose', 0.9)

    def on_fx(self, f):
        k = f[0]
        g = self.g
        if k == 'snd':
            self.app.snd.play(f[1], 0.5)
        elif k == 'proj':
            _, x0, x1, team, kind = f
            name = 'proj_rock' if kind == 'heavy' and g.facs[team] == 'kingdom' else PROJ.get(g.facs[team], 'arrow')
            self.fxs.append(dict(k='proj', x0=x0, x1=x1, team=team, tex=name, age=0.0,
                                 dur=max(0.12, abs(x1 - x0) / 650.0)))
        elif k == 'hit':
            self.fxs.append(dict(k='hit', x=f[1], team=f[2], age=0.0, dur=0.18))
        elif k == 'death':
            self.fxs.append(dict(k='death', x=f[1], team=f[2], age=0.0, dur=0.5))
        elif k == 'ring':
            self.fxs.append(dict(k='ring', x=f[1], r=f[2], team=f[3], style=f[4], age=0.0, dur=0.55))
        elif k == 'cast':
            self.fxs.append(dict(k='label', x=f[1], text=f[2], team=f[3], age=0.0, dur=1.3))

    # -------------------------------------------------------------- mise en page
    def reg(self, name, kind, a, b, c, d=0):
        self.hit.append((name, kind, a, b, c, d))

    def hit_at(self, x, y):
        for name, kind, a, b, c, d in reversed(self.hit):
            if kind == 'r':
                if a <= x <= a + c and b <= y <= b + d:
                    return name
            elif (x - a) ** 2 + (y - b) ** 2 <= c * c:
                return name
        return None

    # -------------------------------------------------------------- dessin
    def draw(self):
        self.canvas.clear()
        self.hit = []
        W, H = Window.width, Window.height
        with self.canvas:
            if self.state == 'menu':
                self.safe(self.draw_menu, W, H)
            elif self.state == 'log':
                self.safe(self.draw_log, W, H)
            elif self.state == 'help':
                self.safe(self.draw_help, W, H)
            elif self.g:
                self.safe(self.draw_world, W, H)
                self.safe(self.draw_hud, W, H, self.state == 'game')
                if self.state == 'pause':
                    self.safe(self.draw_pause, W, H)
                elif self.state == 'end':
                    self.safe(self.draw_end, W, H)
            for (tx, ty) in list(self.tpos.values()):
                Color(1, 1, 0.3, 0.55)
                Line(circle=(tx, ty, dp(26)), width=dp(2))
            text(self.dbg[:90], dp(60), dp(24), dp(9), (0.75, 0.85, 1, 0.9), anchor='l', bold=False)
            err = getattr(self.app, 'last_error', '')
            if err:
                text(err[:110], W / 2, dp(8), dp(9), (1, 0.45, 0.4, 1), bold=False)

    def safe(self, fn, *a):
        try:
            fn(*a)
        except Exception:
            log_error(fn.__name__)

    # ---- fond (ciel, montagnes, collines, herbe, route)
    def backdrop(self, W, H, cam, gy, hy):
        S = W / VIEW_W
        Color(0.36, 0.62, 0.92, 1)
        Rectangle(pos=(0, hy), size=(W, H - hy))
        Color(0.55, 0.78, 0.96, 1)
        Rectangle(pos=(0, hy), size=(W, (H - hy) * 0.5))
        Color(0.72, 0.88, 0.98, 1)
        Rectangle(pos=(0, hy), size=(W, (H - hy) * 0.18))
        for name, fac, hh, dy in (('mtn_far', 0.10, H * 0.30, -0.10), ('hills', 0.25, H * 0.20, -0.30)):
            t = tex(name)
            tw = t.width * (hh / t.height)
            off = -((cam * S * fac) % tw)
            n = int(W / tw) + 2
            for i in range(n):
                pic(name, off + i * tw, hy + hh * dy, tw + 1, hh)
        ts = dp(128)
        off = -((cam * S) % ts)
        rows = int(hy / ts) + 1
        for r in range(rows):
            for c in range(int(W / ts) + 2):
                pic('grass', off + c * ts, r * ts, ts + 1, ts + 1)
        rh = dp(130)
        rs = rh
        off = -((cam * S) % rs)
        for c in range(int(W / rs) + 2):
            pic('dirt', off + c * rs, gy - dp(68), rs + 1, rh, col=(1, 1, 1, 0.9))

    def draw_world(self, W, H):
        g = self.g
        S = W / VIEW_W
        cam = self.cam
        hy = H * 0.50
        gy = H * 0.285
        self.backdrop(W, H, cam, gy, hy)
        # bases
        for t in (0, 1):
            b = g.bases[t]
            name = 'b_%s_hq_%d' % (g.facs[t], t)
            tt = tex(name)
            bw = C.BASE_R * 2.7 * S
            bh = bw * tt.height / float(tt.width)
            bx = (b.x - cam) * S
            if -bw < bx < W + bw:
                col = (1, 0.65, 0.65, 1) if b.flash > 0 else (1, 1, 1, 1)
                Color(0, 0, 0, 0.25)
                Ellipse(pos=(bx - bw * 0.45, gy - dp(14)), size=(bw * 0.9, dp(14)))
                pic(name, bx - bw / 2, gy - dp(10), bw, bh, col=col)
                bar(bx - bw * 0.4, gy - dp(10) + bh + dp(4), bw * 0.8, dp(7), b.hp / b.maxhp,
                    (0.3, 0.9, 0.4, 1) if t == 0 else (0.95, 0.35, 0.3, 1))
        # unites (fond d'abord)
        ents = list(g.units) + [h for h in g.heroes if not h.dead]
        ents.sort(key=lambda e: -e.y)
        for e in ents:
            self.draw_unit(e, S, cam, gy)
        for f in self.fxs:
            self.draw_fx(f, S, cam, gy)

    def draw_unit(self, e, S, cam, gy):
        g = self.g
        cx = (e.x - cam) * S
        W = Window.width
        if cx < -dp(120) or cx > W + dp(120):
            return
        scale = e.scale if e.hero else 1.0
        sz = e.r * 3.4 * S * scale
        kind = e.icon_kind if e.hero else e.kind
        name = 'ic_%s_%s_%d' % (g.facs[e.team], kind, e.team)
        foot = gy + e.y * dp(LANE_DY)
        bob = abs(math.sin(self.t * 9 + e.uid)) * dp(3) if e.moving else 0.0
        lunge = e.face * dp(5) * (e.atk_t / 0.18) if e.atk_t > 0 else 0.0
        Color(0, 0, 0, 0.28)
        Ellipse(pos=(cx - sz * 0.30, foot - dp(3)), size=(sz * 0.6, dp(7)))
        if e.buff:
            Color(1.0, 0.9, 0.3, 0.7)
            Line(ellipse=(cx - sz * 0.32, foot - dp(4), sz * 0.64, dp(9)), width=dp(1.5))
        col = (1, 0.6, 0.6, 1) if e.flash > 0 else (1, 1, 1, 1)
        pic(name, cx - sz / 2 + lunge, foot - sz * 0.12 + bob, sz, sz, flip=e.face < 0, col=col)
        if e.hero or e.hp < e.maxhp:
            bw = sz * (0.8 if e.hero else 0.55)
            bh = dp(6) if e.hero else dp(4)
            by = foot + sz * 0.86
            bar(cx - bw / 2, by, bw, bh, e.hp / e.maxhp,
                (0.3, 0.9, 0.4, 1) if e.team == 0 else (0.95, 0.35, 0.3, 1))
            if e.hero:
                pic(CREST[e.fac], cx - dp(10), by + bh + dp(1), dp(20), dp(20))

    def draw_fx(self, f, S, cam, gy):
        k = f['k']
        p = f['age'] / f['dur']
        x = (f.get('x', f.get('x0', 0)) - cam) * S
        if k == 'proj':
            x0, x1 = f['x0'], f['x1']
            px = (x0 + (x1 - x0) * p - cam) * S
            py = gy + dp(24) + math.sin(math.pi * p) * min(dp(40), abs(x1 - x0) * S * 0.12)
            pic(f['tex'], px - dp(16), py, dp(32), dp(7), flip=x1 < x0)
        elif k == 'hit':
            Color(1, 0.9, 0.5, 1 - p)
            r = dp(7) + dp(10) * p
            Ellipse(pos=(x - r, gy + dp(22) - r), size=(r * 2, r * 2))
        elif k == 'death':
            Color(0.85, 0.85, 0.85, 0.55 * (1 - p))
            r = dp(8) + dp(18) * p
            Ellipse(pos=(x - r, gy + dp(14) + dp(16) * p - r), size=(r * 2, r * 2))
        elif k == 'ring':
            c = RING_COL.get(f['style'], (1, 1, 1))
            Color(c[0], c[1], c[2], 0.9 * (1 - p))
            r = f['r'] * S * (0.35 + 0.65 * p)
            Line(circle=(x, gy + dp(8), r), width=dp(2.5))
            Color(c[0], c[1], c[2], 0.18 * (1 - p))
            Ellipse(pos=(x - r, gy + dp(8) - r), size=(r * 2, r * 2))
        elif k == 'label':
            text(f['text'], x, gy + dp(112) + dp(26) * p, dp(13), (1, 0.95, 0.5, 1 - max(0.0, p - 0.6) * 2.5))

    # ---- interface de jeu
    def draw_hud(self, W, H, live):
        g = self.g
        h = g.heroes[0]
        sd = g.side[0]
        sl, sr = dp(54), dp(14)
        topH = dp(58)
        # barre du haut
        Color(0.04, 0.06, 0.12, 0.78)
        Rectangle(pos=(0, H - topH), size=(W, topH))
        text('Or', sl, H - dp(20), dp(12), (0.9, 0.8, 0.4, 1), anchor='l')
        text(str(int(sd.gold)), sl, H - dp(40), dp(20), (1, 0.9, 0.35, 1), anchor='l')
        pop = g.pop(0)
        text('%d/%d' % (pop, C.POP_MAX), sl + dp(62), H - dp(40), dp(12), (0.8, 0.85, 0.95, 1), anchor='l', bold=False)
        # cartes d'unites
        cw, ch, gap = dp(64), dp(50), dp(5)
        x = sl + dp(104)
        y = H - topH + (topH - ch) / 2
        for kind in C.KINDS:
            st = g.stats[0][kind]
            afford = sd.gold >= st['cost'] and pop < C.POP_MAX
            rrect(x, y, cw, ch, (0.12, 0.16, 0.28, 0.95) if afford else (0.10, 0.11, 0.16, 0.95), dp(7))
            pic('ic_%s_%s_0' % (g.facs[0], kind), x + (cw - dp(34)) / 2, y + dp(15), dp(34), dp(34))
            text(str(st['cost']), x + cw / 2, y + dp(8), dp(11), (1, 0.9, 0.35, 1) if afford else (0.7, 0.5, 0.4, 1))
            n = sd.queue.count(kind)
            if n:
                Color(0.9, 0.3, 0.2, 1)
                Ellipse(pos=(x + cw - dp(14), y + ch - dp(14)), size=(dp(16), dp(16)))
                text(str(n), x + cw - dp(6), y + ch - dp(6), dp(10))
            if sd.queue and sd.queue[0] == kind:
                bar(x + dp(4), y + dp(2), cw - dp(8), dp(3), sd.prod_t / st['time'], (0.4, 0.8, 1, 1))
            if live:
                self.reg('card_' + kind, 'r', x, y, cw, ch)
            x += cw + gap
        # pause
        pw = dp(42)
        px = W - sr - pw
        py = H - topH + (topH - pw) / 2
        rrect(px, py, pw, pw, (0.12, 0.16, 0.28, 0.95), dp(7))
        pic('i_pause', px + dp(7), py + dp(7), pw - dp(14), pw - dp(14))
        if live:
            self.reg('pause', 'r', px - dp(6), py - dp(6), pw + dp(12), pw + dp(12))
        text('v' + C.VERSION, px - dp(10), H - dp(14), dp(9), (0.7, 0.75, 0.85, 1), anchor='r', bold=False)
        # etat du heros
        hx = x + dp(8)
        hw = px - dp(14) - hx
        if hw > dp(90):
            bw_ = min(hw, dp(170))
            text('%s  Niv. %d' % (h.name, h.level), hx, H - dp(15), dp(12), (1, 0.95, 0.6, 1), anchor='l')
            bar(hx, H - dp(31), bw_, dp(9), h.hp / h.maxhp, (0.3, 0.9, 0.4, 1))
            bar(hx, H - dp(42), bw_, dp(5), C.hero_xp_frac(h), (0.35, 0.6, 1, 1))
            if h.dead:
                text('Retour dans %d s (%d or)' % (max(0, int(h.dead_t) + 1), C.HERO_REVIVE_COST), hx, H - dp(53),
                     dp(10), (1, 0.6, 0.5, 1), anchor='l')
            elif h.points > 0:
                text('%d point%s : touchez un +' % (h.points, 's' if h.points > 1 else ''), hx, H - dp(53), dp(10),
                     (1, 0.9, 0.35, 1), anchor='l')
        # mini-barre du couloir
        mw = min(dp(380), W * 0.42)
        mx = W / 2 - mw / 2
        my = H - topH - dp(14)
        Color(0, 0, 0, 0.5)
        Rectangle(pos=(mx - dp(3), my - dp(3)), size=(mw + dp(6), dp(12)))
        Color(0.3, 0.45, 0.3, 0.9)
        Rectangle(pos=(mx, my), size=(mw, dp(6)))
        for u in g.units:
            Color(0.4, 0.8, 1, 1) if u.team == 0 else Color(1, 0.45, 0.4, 1)
            Rectangle(pos=(mx + mw * u.x / C.LENGTH - dp(1.5), my), size=(dp(3), dp(6)))
        for t in (0, 1):
            Color(0.2, 0.6, 1, 1) if t == 0 else Color(1, 0.3, 0.25, 1)
            Rectangle(pos=(mx + mw * g.bases[t].x / C.LENGTH - dp(3), my - dp(2)), size=(dp(6), dp(10)))
            hh = g.heroes[t]
            if not hh.dead:
                Color(1, 0.9, 0.3, 1)
                Ellipse(pos=(mx + mw * hh.x / C.LENGTH - dp(3.5), my - dp(0.5)), size=(dp(7), dp(7)))
        Color(1, 1, 1, 0.8)
        Line(rectangle=(mx + mw * max(0.0, self.cam) / C.LENGTH, my - dp(2), mw * VIEW_W / C.LENGTH, dp(10)),
             width=dp(1))
        if g.time > C.SUDDEN_T and g.winner is None:
            text('Épuisement : les bases s\'affaiblissent', W / 2, my - dp(18), dp(11), (1, 0.55, 0.4, 1))
        # aide de depart
        if self.game_t < 12 and live:
            a = 1.0 if self.game_t < 8 else max(0.0, (12 - self.game_t) / 4)
            text('Pouce gauche : déplace le héros (haut, bas, gauche, droite)', W / 2, H * 0.60, dp(13), (1, 1, 1, a))
            text('Bouton rouge : attaque - cercles dorés : sorts (voir Aide)', W / 2, H * 0.60 - dp(20), dp(13),
                 (1, 1, 1, a))
            text('En haut : touche une unité pour la produire (appui long = 5)', W / 2, H * 0.60 - dp(40), dp(13),
                 (1, 1, 1, a))
            text('Touchez un + doré pour apprendre votre premier sort', W / 2, H * 0.60 - dp(60), dp(13), (1, 0.9, 0.4, a))
        # attitudes
        ar = dp(46)
        ax = W - sr - ar
        ay = dp(14) + ar
        D = dp(100)
        sr_ = dp(35)
        xr = ax - D - sr_ - dp(10)
        xl = sl + dp(250)
        if live:
            self.reg('stickzone', 'r', 0, 0, xl, H * 0.5)
        n = len(C.STANCES)
        gp = dp(8)
        bw = max(dp(50), min(dp(104), (xr - xl - gp * (n - 1)) / n))
        bh = dp(46)
        x = xl + max(0.0, (xr - xl - (bw * n + gp * (n - 1))) / 2)
        for s in C.STANCES:
            on = sd.stance == s
            rrect(x, dp(12), bw, bh, (0.25, 0.32, 0.55, 0.95) if on else (0.08, 0.10, 0.18, 0.88), dp(8))
            if on:
                Color(1, 0.85, 0.3, 1)
                Line(rounded_rectangle=(x, dp(12), bw, bh, dp(8)), width=dp(1.8))
            pic(STANCE_ICON[s], x + (bw - dp(24)) / 2, dp(12) + bh - dp(28), dp(24), dp(24))
            text(C.STANCE_NAMES[s], x + bw / 2, dp(12) + dp(9), dp(10), (1, 1, 1, 1) if on else (0.8, 0.85, 0.95, 1))
            if live:
                self.reg('stance_' + s, 'r', x, dp(8), bw, bh + dp(8))
            x += bw + gp
        # bouton d'attaque et sorts
        held = self.atk
        Color(0.75, 0.2, 0.15, 0.95) if held else Color(0.55, 0.14, 0.12, 0.85)
        Ellipse(pos=(ax - ar, ay - ar), size=(ar * 2, ar * 2))
        Color(1, 0.8, 0.5, 0.9)
        Line(circle=(ax, ay, ar), width=dp(2))
        pic('i_army', ax - ar * 0.42, ay - ar * 0.30, ar * 0.84, ar * 0.84)
        text('ATTAQUE', ax, ay - ar * 0.56, dp(11))
        if live:
            self.reg('atk', 'c', ax, ay, ar * 1.08)
        sp_pos = [(ax + D * math.cos(math.radians(an)), ay + D * math.sin(math.radians(an))) for an in (174, 127, 82)]
        sp_pos.append((ax - dp(166), ay + dp(96)))
        for i, (scx, scy) in enumerate(sp_pos):
            sp = h.spells[i]
            learned = sp['lv'] > 0
            ready = learned and sp['cdt'] <= 0 and not h.dead
            Color(0.10, 0.13, 0.24, 0.92)
            Ellipse(pos=(scx - sr_, scy - sr_), size=(sr_ * 2, sr_ * 2))
            pic(sp['icon'], scx - sr_ * 0.5, scy - sr_ * 0.30, sr_ * 1.0, sr_ * 1.0,
                col=(1, 1, 1, 1) if learned else (0.55, 0.55, 0.6, 0.85))
            if not learned:
                Color(0, 0, 0, 0.45)
                Ellipse(pos=(scx - sr_, scy - sr_), size=(sr_ * 2, sr_ * 2))
                if sp['ult'] and h.level < C.ULT_LEVEL:
                    text('Niv. %d' % C.ULT_LEVEL, scx, scy + sr_ * 0.2, dp(11), (1, 0.8, 0.5, 1))
            elif sp['cdt'] > 0 and sp['cd'] > 0:
                Color(0, 0, 0, 0.62)
                Ellipse(pos=(scx - sr_, scy - sr_), size=(sr_ * 2, sr_ * 2), angle_start=0,
                        angle_end=360.0 * sp['cdt'] / sp['cd'])
                text(str(int(sp['cdt']) + 1), scx, scy + sr_ * 0.18, dp(16))
            elif h.dead:
                Color(0, 0, 0, 0.5)
                Ellipse(pos=(scx - sr_, scy - sr_), size=(sr_ * 2, sr_ * 2))
            text(sp['short'], scx, scy - sr_ * 0.62, dp(8.5), (1, 1, 1, 1) if ready else (0.7, 0.75, 0.85, 1))
            for q in range(sp['maxlv']):
                px_ = scx + (q - (sp['maxlv'] - 1) / 2.0) * dp(9)
                Color(1, 0.85, 0.3, 1) if q < sp['lv'] else Color(0.3, 0.33, 0.42, 1)
                Ellipse(pos=(px_ - dp(2.6), scy + sr_ * 0.82 - dp(2.6)), size=(dp(5.2), dp(5.2)))
            if ready:
                Color(1, 0.85, 0.3, 1)
            elif learned:
                Color(0.5, 0.55, 0.65, 1)
            else:
                Color(0.28, 0.30, 0.38, 1)
            Line(circle=(scx, scy, sr_), width=dp(1.8))
            if live and learned:
                self.reg('spell_%d' % i, 'c', scx, scy, sr_ * 1.12)
            if g.can_learn(0, i):
                bx, by = scx + sr_ * 0.74, scy + sr_ * 0.74
                br = dp(13) + dp(2) * math.sin(self.t * 6)
                Color(0.95, 0.75, 0.15, 1)
                Ellipse(pos=(bx - br, by - br), size=(br * 2, br * 2))
                Color(0.2, 0.12, 0, 1)
                Line(circle=(bx, by, br), width=dp(1.4))
                text('+', bx, by, dp(18), (0.2, 0.1, 0, 1))
                if live:
                    self.reg('learn_%d' % i, 'c', bx, by, dp(21))
        # manette (deplacement dans toutes les directions)
        if self.stick:
            _, ox, oy = self.stick
            vx, vy = self.move, self.my
        else:
            ox, oy, vx, vy = sl + dp(110), dp(100), 0.0, 0.0
        Color(1, 1, 1, 0.16 if self.stick else 0.10)
        Ellipse(pos=(ox - dp(56), oy - dp(56)), size=(dp(112), dp(112)))
        Color(1, 1, 1, 0.35)
        Line(circle=(ox, oy, dp(56)), width=dp(1.5))
        Color(1, 1, 1, 0.45)
        Triangle(points=[ox - dp(46), oy, ox - dp(34), oy + dp(8), ox - dp(34), oy - dp(8)])
        Triangle(points=[ox + dp(46), oy, ox + dp(34), oy + dp(8), ox + dp(34), oy - dp(8)])
        Triangle(points=[ox, oy + dp(46), ox - dp(8), oy + dp(34), ox + dp(8), oy + dp(34)])
        Triangle(points=[ox, oy - dp(46), ox - dp(8), oy - dp(34), ox + dp(8), oy - dp(34)])
        Color(1, 1, 1, 0.55 if self.stick else 0.3)
        Ellipse(pos=(ox + vx * dp(34) - dp(22), oy + vy * dp(34) - dp(22)), size=(dp(44), dp(44)))

    # ---- ecrans
    def panel(self, W, H, w, h):
        Color(0, 0, 0, 0.55)
        Rectangle(pos=(0, 0), size=(W, H))
        x, y = (W - w) / 2, (H - h) / 2
        rrect(x, y, w, h, (0.07, 0.10, 0.20, 0.96), dp(14))
        Color(0.9, 0.75, 0.3, 1)
        Line(rounded_rectangle=(x, y, w, h, dp(14)), width=dp(2))
        return x, y

    def button(self, name, label, cx, cy, w, h, col=(0.16, 0.24, 0.46, 1), fs=None, on=False):
        x, y = cx - w / 2, cy - h / 2
        rrect(x, y, w, h, col, dp(10))
        if on:
            Color(1, 0.85, 0.3, 1)
            Line(rounded_rectangle=(x, y, w, h, dp(10)), width=dp(2))
        text(label, cx, cy, fs or dp(16))
        self.reg(name, 'r', x, y, w, h)

    def draw_menu(self, W, H):
        cam = self.t * 40.0
        self.backdrop(W, H, cam, H * 0.285, H * 0.50)
        Color(0, 0, 0, 0.35)
        Rectangle(pos=(0, 0), size=(W, H))
        e = dp(70)
        pic('em_kingdom', W * 0.5 - dp(190) - e, H * 0.60, e, e)
        pic('em_horde', W * 0.5 + dp(190), H * 0.60, e, e)
        text('Le Chemin des Rois', W / 2, H * 0.80, dp(38), (1, 0.92, 0.55, 1))
        text('Royaume d\'Aurèle  contre  Horde de Gorak', W / 2, H * 0.68, dp(15), (0.9, 0.95, 1, 1))
        self.button('play', 'Jouer', W / 2, H * 0.50, dp(220), dp(56), (0.2, 0.5, 0.25, 1), dp(24))
        for i in range(3):
            self.button('d%d' % i, DIFF_NAMES[i], W / 2 + (i - 1) * dp(118), H * 0.34, dp(108), dp(38),
                        (0.16, 0.24, 0.46, 1), dp(14), on=self.diff == i)
        snd = self.app.snd
        self.button('help', 'Aide', W / 2 - dp(170), H * 0.20, dp(150), dp(36), (0.14, 0.18, 0.32, 1), dp(13))
        self.button('snd', 'Son : oui' if (snd.sound or snd.music_on) else 'Son : non', W / 2, H * 0.20,
                    dp(150), dp(36), (0.14, 0.18, 0.32, 1), dp(13))
        self.button('log', 'Journal', W / 2 + dp(170), H * 0.20, dp(150), dp(36), (0.14, 0.18, 0.32, 1), dp(13))
        text('Jalon %s' % C.VERSION, dp(60), dp(26), dp(11), (0.8, 0.85, 0.95, 1), anchor='l', bold=False)

    def draw_pause(self, W, H):
        x, y = self.panel(W, H, dp(300), dp(310))
        text('Pause', W / 2, y + dp(275), dp(24), (1, 0.92, 0.55, 1))
        self.button('resume', 'Reprendre', W / 2, y + dp(220), dp(220), dp(46), (0.2, 0.5, 0.25, 1))
        self.button('phelp', 'Aide', W / 2, y + dp(165), dp(220), dp(42), (0.16, 0.24, 0.46, 1), dp(14))
        self.button('plog', 'Journal d\'erreurs', W / 2, y + dp(110), dp(220), dp(42), (0.16, 0.24, 0.46, 1), dp(14))
        self.button('quit', 'Quitter la partie', W / 2, y + dp(55), dp(220), dp(42), (0.5, 0.18, 0.15, 1), dp(14))

    def draw_end(self, W, H):
        g = self.g
        win = g.winner == 0
        x, y = self.panel(W, H, dp(340), dp(270))
        text('Victoire !' if win else 'Défaite', W / 2, y + dp(228), dp(30),
             (0.5, 1, 0.5, 1) if win else (1, 0.5, 0.45, 1))
        m, s = divmod(int(g.time), 60)
        text('Durée : %d min %02d s' % (m, s), W / 2, y + dp(188), dp(14), (0.9, 0.95, 1, 1), bold=False)
        text('Ennemis vaincus : %d  -  Héros niveau %d' % (g.kills[0], g.heroes[0].level), W / 2, y + dp(166), dp(14),
             (0.9, 0.95, 1, 1), bold=False)
        self.button('again', 'Rejouer', W / 2, y + dp(112), dp(220), dp(46), (0.2, 0.5, 0.25, 1))
        self.button('emenu', 'Menu', W / 2, y + dp(55), dp(220), dp(42), (0.16, 0.24, 0.46, 1), dp(14))

    def draw_help(self, W, H):
        Color(0.04, 0.06, 0.10, 1)
        Rectangle(pos=(0, 0), size=(W, H))
        page = self.help_page
        text('Aide - %s' % ('commandes et progression' if page == 0 else 'sorts des héros'), W / 2, H - dp(26), dp(20),
             (1, 0.92, 0.55, 1))
        if page == 0:
            lines = ['COMMANDES',
                     'Pouce gauche : déplace le héros dans toutes les directions (monter et descendre permet de contourner ou de viser).',
                     'Bouton rouge ATTAQUE : le héros frappe. À l\'arrêt, il frappe tout seul ; maintenez le bouton pour frapper en marchant.',
                     'Cartes en haut : produire une unité (appui long = 5). Le chiffre est le coût en or.',
                     'Boutons du bas : ordre donné à toute l\'armée. Tenir : reste près de la base. Avancer : attaque. '
                     'Retraite : revient à la base. Suivre : reste autour du héros.',
                     'PROGRESSION DU HÉROS',
                     'Le héros gagne de l\'expérience quand des ennemis meurent près de lui (barre bleue sous sa vie). '
                     'Niveau maximum : 10. À chaque niveau : +1 point de compétence, plus de vie et de dégâts.',
                     'Au début, aucun sort n\'est appris : touchez le + doré d\'un sort pour dépenser un point. '
                     'Les petits points sous chaque sort indiquent son niveau.',
                     'Un sort passe au niveau 2 avec le niveau de héros 3, et au niveau 3 avec le niveau 5. '
                     'Le sort ultime (cercle isolé en haut à gauche des sorts) se débloque au niveau de héros 6.',
                     'Le chiffre sur un sort est le nombre de secondes avant de pouvoir le relancer.']
            y = H - dp(58)
            for ln in lines:
                head = ln.isupper()
                _, hh = text(ln, dp(60), y, dp(11.5) if head else dp(10.5), (1, 0.9, 0.45, 1) if head else (0.9, 0.95, 1, 1),
                             anchor='l', bold=head, wrap=W - dp(100), halign='left')
                y -= hh + dp(7 if head else 5)
        else:
            colw = (W - dp(120)) / 2
            for ci, fac in enumerate(('kingdom', 'horde')):
                x0 = dp(60) + ci * (colw + dp(20))
                hd = C.HEROES[fac]
                y = H - dp(62)
                text('%s (%s - %s)' % (hd['name'], C.FACTIONS[fac]['short'], 'votre héros' if ci == 0 else 'héros ennemi'),
                     x0, y, dp(13), (1, 0.9, 0.45, 1), anchor='l')
                yy = y - dp(30)
                for sp in list(hd['spells']) + [hd['ultimate']]:
                    ult = sp is hd['ultimate']
                    pic(sp['icon'], x0, yy - dp(20), dp(34), dp(34))
                    text(sp['name'] + (' (ultime)' if ult else ''), x0 + dp(42), yy, dp(11.5), anchor='l')
                    text('recharge %d s' % int(sp['cd']), x0 + colw, yy, dp(9.5), (0.7, 0.8, 0.95, 1), anchor='r',
                         bold=False)
                    _, hh = text(sp['desc'], x0 + dp(42), yy - dp(15), dp(9.5), (0.88, 0.92, 1, 1), anchor='l',
                                 bold=False, wrap=colw - dp(48), halign='left')
                    yy -= dp(15) + hh + dp(12)
        self.button('hback', 'Retour', W / 2 - dp(100), dp(34), dp(160), dp(38), (0.16, 0.24, 0.46, 1), dp(14))
        self.button('hnext', 'Sorts >' if page == 0 else '< Commandes', W / 2 + dp(100), dp(34), dp(160), dp(38),
                    (0.14, 0.18, 0.32, 1), dp(14))

    def draw_log(self, W, H):
        Color(0.04, 0.06, 0.10, 1)
        Rectangle(pos=(0, 0), size=(W, H))
        text('Journal d\'erreurs', W / 2, H - dp(34), dp(20), (1, 0.92, 0.55, 1))
        lines = list(ERRS)
        if not lines:
            lines = ['Aucune erreur enregistrée dans cette session.']
        s = '\n'.join(lines[-9:])
        text(s, dp(60), H - dp(70), dp(10), (0.9, 0.95, 1, 1), anchor='l', bold=False, wrap=W - dp(90),
             halign='left')
        self.button('lback', 'Retour', W / 2 - dp(100), dp(40), dp(160), dp(40), (0.16, 0.24, 0.46, 1), dp(14))
        self.button('lclear', 'Effacer', W / 2 + dp(100), dp(40), dp(160), dp(40), (0.5, 0.18, 0.15, 1), dp(14))

    # -------------------------------------------------------------- touchers (captes au niveau de la fenetre)
    def t_down(self, win, touch):
        return self.down(touch)

    def on_touch_down(self, touch):          # voie de secours : le widget racine recoit aussi les touchers
        return self.down(touch)

    def down(self, touch):
        try:
            if str(getattr(touch, 'button', 'left')).startswith('scroll'):
                return False
            x, y = touch.x, touch.y
            self.tpos[touch.uid] = (x, y)
            name = self.hit_at(x, y)
            self.dbg = 'toucher %d,%d -> %s (zones %d, écran %dx%d)' % (x, y, name, len(self.hit),
                                                                      Window.width, Window.height)
            if name is None:
                return False
            return self.press(name, touch.uid, x, y)
        except Exception:
            log_error('t_down')
            return False

    def press(self, name, uid, x, y):
        g = self.g
        snd = self.app.snd
        st = self.state
        if st == 'menu':
            if name == 'play':
                snd.play('sfx_click')
                self.start()
            elif name.startswith('d') and name[1:].isdigit():
                self.diff = int(name[1:])
                snd.play('sfx_click')
            elif name == 'snd':
                snd.toggle()
                snd.music('music_menu', 0.4)
            elif name == 'log':
                self.state = 'log'
                self.back_to = 'menu'
            elif name == 'help':
                self.state = 'help'
                self.help_page = 0
                self.back_to = 'menu'
            return True
        if st == 'help':
            if name == 'hback':
                self.state = self.back_to
            elif name == 'hnext':
                self.help_page = 1 - self.help_page
            return True
        if st == 'log':
            if name == 'lback':
                self.state = self.back_to
            elif name == 'lclear':
                del ERRS[:]
                _ERR.clear()
                if self.app:
                    self.app.last_error = ''
            return True
        if st == 'pause':
            if name == 'resume':
                self.state = 'game'
            elif name == 'plog':
                self.state = 'log'
                self.back_to = 'pause'
            elif name == 'phelp':
                self.state = 'help'
                self.help_page = 0
                self.back_to = 'pause'
            elif name == 'quit':
                self.to_menu()
            return True
        if st == 'end':
            if name == 'again':
                self.start()
            elif name == 'emenu':
                self.to_menu()
            return True
        # en partie
        if name == 'pause':
            self.state = 'pause'
            self.roles, self.stick, self.move, self.atk = {}, None, 0.0, False
        elif name.startswith('card_'):
            kind = name[5:]
            if g.queue_unit(0, kind):
                snd.play('sfx_click', 0.5)
            self.hold = (uid, kind, self.t, False)
            self.roles[uid] = 'card'
        elif name.startswith('stance_'):
            g.set_stance(0, name[7:])
            snd.play('sfx_click', 0.5)
        elif name.startswith('learn_'):
            g.learn(0, int(name[6:]))
        elif name.startswith('spell_'):
            g.cast(0, int(name[6:]))
        elif name == 'atk':
            self.atk = True
            self.roles[uid] = 'atk'
        elif name == 'stickzone' and self.stick is None:
            sl = dp(54)
            ox = max(sl + dp(50), min(sl + dp(250) - dp(50), x))
            self.stick = (uid, ox, y)
            self.roles[uid] = 'stick'
            self.move = 0.0
        return True

    def t_move(self, win, touch):
        return self.move_ev(touch)

    def on_touch_move(self, touch):
        return self.move_ev(touch)

    def move_ev(self, touch):
        try:
            if touch.uid in self.tpos:
                self.tpos[touch.uid] = (touch.x, touch.y)
            if self.roles.get(touch.uid) == 'stick' and self.stick:
                _, ox, oy = self.stick
                v = max(-1.0, min(1.0, (touch.x - ox) / dp(46)))
                w = max(-1.0, min(1.0, (touch.y - oy) / dp(46)))
                self.move = 0.0 if abs(v) < 0.18 else v
                self.my = 0.0 if abs(w) < 0.18 else w
                return True
        except Exception:
            log_error('t_move')
        return False

    def t_up(self, win, touch):
        return self.up_ev(touch)

    def on_touch_up(self, touch):
        return self.up_ev(touch)

    def up_ev(self, touch):
        try:
            self.tpos.pop(touch.uid, None)
            role = self.roles.pop(touch.uid, None)
            if role == 'stick':
                self.stick = None
                self.move = 0.0
                self.my = 0.0
            elif role == 'atk':
                self.atk = False
            elif role == 'card':
                self.hold = None
            return role is not None
        except Exception:
            log_error('t_up')
        return False

    def on_key(self, win, key, *a):
        try:
            if key == 27:
                if self.state == 'game':
                    self.state = 'pause'
                    self.roles, self.stick, self.move, self.atk = {}, None, 0.0, False
                    return True
                if self.state == 'pause':
                    self.state = 'game'
                    return True
                if self.state in ('log', 'help'):
                    self.state = self.back_to
                    return True
                if self.state == 'end':
                    self.to_menu()
                    return True
        except Exception:
            log_error('on_key')
        return False

    back_to = 'menu'
    help_page = 0


class ChemRoisApp(App):
    title = 'Chemin des Rois'

    def build(self):
        global APP
        APP = self
        self.last_error = ''
        try:
            ExceptionManager.add_handler(_Handler())
        except Exception:
            pass
        self.snd = Snd(os.path.join(self.user_data_dir, 'snd'))
        try:
            Window.clearcolor = (0.04, 0.06, 0.10, 1)
        except Exception:
            pass
        self.view = GameView(self)
        return self.view

    def on_pause(self):
        return True


if __name__ == '__main__':
    ChemRoisApp().run()
