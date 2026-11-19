#!/usr/bin/env python3
"""
RunPulse — Helper di autenticazione Garmin Connect per bypassare il blocco 403 dei server cloud.
Esegui questo script sul tuo Mac/PC di casa (richiede python 3).
Genera la stringa di sessione sicura da incollare su RunPulse in 'Connessioni'.
"""
import getpass
import json
from pathlib import Path
import sys

try:
    from garminconnect import Garmin
except ImportError:
    print("Installazione dipendenza garminconnect...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "garminconnect", "curl_cffi"])
    from garminconnect import Garmin


def main():
    print("=" * 65)
    print("🏃 RunPulse — Generatore Token Garmin Connect")
    print("Questo script si collega dalla tua connessione di casa (IP residenziale)")
    print("dove Garmin NON blocca l'accesso, e genera il token per RunPulse.")
    print("=" * 65)

    email = input("\nInserisci la tua email Garmin Connect: ").strip()
    password = getpass.getpass("Inserisci la tua password Garmin Connect: ")

    if not email or not password:
        print("Email e password sono obbligatorie.")
        sys.exit(1)

    print("\nAccesso a Garmin Connect in corso...")

    def prompt_mfa():
        return input("\nInserisci il codice di verifica MFA ricevuto via SMS/email: ").strip()

    try:
        token_dir = Path("./temp_garmin_tokens")
        token_dir.mkdir(exist_ok=True)

        try:
            client = Garmin(email, password, prompt_mfa=prompt_mfa)
        except TypeError:
            client = Garmin(email, password)
            client.prompt_mfa = prompt_mfa

        if hasattr(client, "garth"):
            client.garth.login(email, password, prompt_mfa=prompt_mfa)
            client.garth.dump(str(token_dir))
        else:
            client.login()
            if hasattr(client, "dump"):
                client.dump(str(token_dir))

        o1_file = token_dir / "oauth1_token.json"
        o2_file = token_dir / "oauth2_token.json"

        o1 = json.loads(o1_file.read_text(encoding="utf-8")) if o1_file.exists() else {}
        o2 = json.loads(o2_file.read_text(encoding="utf-8")) if o2_file.exists() else {}

        # Cleanup temporary files
        for f in token_dir.glob("*"):
            f.unlink()
        token_dir.rmdir()

        payload = json.dumps({"oauth1": o1, "oauth2": o2})

        print("\n" + "🎉 " * 15)
        print("ACCESSO RIUSCITO! Ecco il tuo token di sessione:")
        print("=" * 65)
        print(payload)
        print("=" * 65)
        print("\n👉 COPIA IL TESTO TRA LE DUE RIGHE SOPRA,")
        print("vai su RunPulse in 'Connessioni', clicca su '🔑 Incolla Token di Sessione'")
        print("e incollalo per collegare Garmin definitivamente senza blocchi cloud!")
        print("=" * 65 + "\n")

    except Exception as e:
        print(f"\n❌ Errore durante l'accesso a Garmin: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
