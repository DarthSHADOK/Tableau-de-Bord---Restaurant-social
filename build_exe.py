import os
import shutil
import subprocess
import sys
import platform
import time

def clean_previous_builds():
    """Nettoie les anciens dossiers de compilation."""
    print("🧹 Nettoyage des fichiers précédents...")
    folders = ["build", "dist"]
    files = ["GestionResto.spec"]

    for folder in folders:
        if os.path.exists(folder):
            try:
                shutil.rmtree(folder)
                print(f"   - Dossier '{folder}' supprimé.")
            except Exception as e:
                print(f"   ! Impossible de supprimer '{folder}': {e}")

    for file in files:
        if os.path.exists(file):
            try:
                os.remove(file)
                print(f"   - Fichier '{file}' supprimé.")
            except Exception as e:
                print(f"   ! Impossible de supprimer '{file}': {e}")

def compile_app():
    """Lance la compilation PyInstaller."""
    print("\n🚀 Démarrage de la compilation...")

    # Vérification du dossier Images
    if not os.path.exists("Images"):
        print("❌ ERREUR : Le dossier 'Images' est introuvable !")
        print("   Veuillez renommer votre dossier 'Assets' en 'Images'.")
        input("Appuyez sur Entrée pour quitter...")
        sys.exit(1)

    # Détection du séparateur pour --add-data (; sous Windows, : sous Linux)
    system_os = platform.system()
    separator = ";" if system_os == "Windows" else ":"
    
    # Commande PyInstaller
    # Equivalent à : pyinstaller --noconsole --onefile --clean --name="GestionResto" ...
    command = [
        sys.executable, "-m", "PyInstaller", # Utilise le python courant
        "--noconsole",
        "--onefile",
        "--clean",
        "--name=GestionResto",
        "--icon=Images/logo.ico",
        f"--add-data=Images{separator}Images", # Inclusion dynamique des images
        "main.py"
    ]

    try:
        # Lancement de la commande
        subprocess.check_call(command)
        print("\n✅ COMPILATION TERMINÉE AVEC SUCCÈS !")
        
        # Ouvrir le dossier dist à la fin
        dist_path = os.path.abspath("dist")
        if os.path.exists(dist_path):
            print(f"📂 Ouverture du dossier : {dist_path}")
            if system_os == "Windows":
                os.startfile(dist_path)
            elif system_os == "Linux":
                subprocess.call(["xdg-open", dist_path])
            elif system_os == "Darwin": # macOS
                subprocess.call(["open", dist_path])
                
    except subprocess.CalledProcessError:
        print("\n❌ ERREUR PENDANT LA COMPILATION.")
    except Exception as e:
        print(f"\n❌ ERREUR IMPRÉVUE : {e}")

if __name__ == "__main__":
    print("============================================")
    print(f"   SCRIPT DE COMPILATION ({platform.system()})")
    print("============================================")
    
    clean_previous_builds()
    compile_app()
    
    print("\nTerminé.")
    if platform.system() == "Windows":
        input("Appuyez sur Entrée pour fermer...")