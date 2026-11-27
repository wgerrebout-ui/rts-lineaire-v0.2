[app]
title = Chemin des Rois
package.name = cheminrois
package.domain = org.cheminrois
source.dir = .
source.include_exts = py
source.exclude_dirs = tests
version = 0.2
requirements = python3,kivy
orientation = landscape
presplash.filename = %(source.dir)s/presplash.png
icon.filename = %(source.dir)s/icon.png
android.presplash_color = #0a0e18
fullscreen = 1
android.permissions = INTERNET
android.api = 33
android.minapi = 21
android.ndk = 25b
android.ndk_api = 21
android.archs = arm64-v8a
android.accept_sdk_license = True
p4a.branch = v2024.01.21

[buildozer]
log_level = 2
warn_on_root = 1
