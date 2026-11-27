LE CHEMIN DES ROIS - jalon 0.2

Contenu : un couloir, deux bases (Royaume joueur / Horde IA), un heros par camp (Paladin / Berserker),
4 types d'unites, 4 attitudes (Tenir, Avancer, Retraite, Suivre), 3 sorts de heros, IA adverse (3 difficultes).

Commandes : pouce gauche = deplacer le heros ; a droite = attaque et 3 sorts ;
en haut = produire une unite (appui long = 5) ; en bas = attitude de l'armee.

Fichiers
  main.py        interface Kivy (dessin par canvas, touchers captes au niveau de la fenetre)
  corridor.py    moteur de jeu (Python pur, sans Kivy)
  assets_data.py / sounds_data.py   images et sons integres (issus du RTS)
  tests/         simulations sans interface (sim_test.py, api_test.py, fake_kivy_test.py)

Compilation : deposer ces fichiers a la racine du depot GitHub -> onglet Actions -> "Build APK"
-> telecharger l'artefact "cheminrois-apk".

Tests (facultatif, sur PC) : python tests/sim_test.py 10
Journal d'erreurs : menu > Journal, ou pause > Journal d'erreurs (fichier crash.log dans le dossier de l'appli).

v0.1.1 : captation des touchers renforcee (deux voies) + ligne de diagnostic en bas a gauche (dernier toucher et bouton touche) + cercle jaune sous chaque doigt.

v0.1.2 : deplacement du heros en profondeur (manette 2D), sorts nommes + ecran Aide (menu et pause), rythme ralenti de 15 %,
difficulte revue (Facile = adversaire nettement plus faible, Difficile = plus dur).

v0.1.3 : le heros n'encaisse plus tout (les ennemis preferent une unite proche ; attitude Suivre : corps a corps devant le heros, archers derriere).

v0.2 : progression du heros. Experience (ennemis morts pres du heros), niveaux 1 a 10 (+1 point de competence, + vie et degats),
3 sorts a 3 niveaux a apprendre (bouton + dore), ultime au niveau 6 (Benediction royale / Fureur de Gorak),
niveau et barre d'experience dans la barre du haut, aide en deux pages. Le heros adverse progresse aussi (moins vite en Facile).
