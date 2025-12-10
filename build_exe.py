import os
import shutil
import subprocess
import sys
import platform

def clean_previous_builds():
    print("🧹 Nettoyage des anciens fichiers...")
    for folder in ["build", "dist"]:
        if os.path.exists(folder):
            try: shutil.rmtree(folder)
            except: pass
    if os.path.exists("GestionResto.spec"):
        try: os.remove("GestionResto.spec")
        except: pass

def compile_app():
    print("\n🚀 Démarrage de la compilation (Mode FICHIER UNIQUE / TRANSITION)...")

    if not os.path.exists("Images"):
        print("❌ ERREUR : Le dossier 'Images' est introuvable !")
        sys.exit(1)

    # Séparateur selon l'OS
    separator = ";" if platform.system() == "Windows" else ":"
    
    # Commande PyInstaller
    # --onefile : Crée un seul fichier .exe (Compatible avec votre ancien updater)
    # Pas de dossier DB inclus.
    command = [
        sys.executable, "-m", "PyInstaller",
        "--noconsole",
        "--onefile",         # <--- C'EST ICI : Fichier unique demandé
        "--clean",
        "--name=GestionResto",
        "--icon=Images/logo.ico",
        f"--add-data=Images{separator}Images",
        "main.py"
    ]

    try:
        subprocess.check_call(command)
        print("\n✅ COMPILATION TERMINÉE !")
        print("   Le fichier se trouve ici : dist/GestionResto.exe")
        print("   -> C'est ce fichier .exe que vous devez uploader pour la v1.1.3")

        # Ouverture automatique du dossier
        if platform.system() == "Windows":
            os.startfile(os.path.abspath("dist"))
                
    except Exception as e:
        print(f"\n❌ ERREUR : {e}")

if __name__ == "__main__":
    clean_previous_builds()
    compile_app()
    if platform.system() == "Windows":
        input("Appuyez sur Entrée pour fermer...")