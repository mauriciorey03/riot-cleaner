"""Limpia la lista de amigos de Riot usando la API local del Riot Client.

Uso:
    python riot_friends_cleaner.py                 # simulación: genera candidatos.csv y dashboard.html, no borra nada
    python riot_friends_cleaner.py --apply         # elimina a los marcados 'si' en candidatos.csv
Opciones:
    --days N          inactividad mínima en días para ser candidato (por defecto 365)
    --keep-notes      no eliminar amigos que tengan nota
    --keep-group G    no eliminar amigos de ese grupo (se puede repetir)
    --no-null         no considerar candidatos a quienes no tienen fecha de última conexión
    --csv RUTA        CSV a usar con --apply (por ejemplo, el exportado desde el dashboard)
    --reset           ignora la selección guardada en candidatos.csv

Requiere el Riot Client abierto y con sesión iniciada.
"""
import argparse
import base64
import csv
import datetime as dt
import json
import os
import ssl
import sys
import time
import urllib.request

LOCKFILE = os.path.expandvars(r"%LOCALAPPDATA%\Riot Games\Riot Client\Config\lockfile")
HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, "candidatos.csv")
BACKUP_DIR = os.path.join(HERE, "backups")


class RiotClient:
    def __init__(self):
        if not os.path.exists(LOCKFILE):
            sys.exit("No se encontró el lockfile: abre el Riot Client e inicia sesión.")
        _, _, port, pw, _ = open(LOCKFILE, encoding="utf-8").read().split(":")
        self.base = f"https://127.0.0.1:{port}"
        self.auth = "Basic " + base64.b64encode(f"riot:{pw}".encode()).decode()
        self.ctx = ssl._create_unverified_context()  # certificado autofirmado local

    def request(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Authorization": self.auth,
                                              "Content-Type": "application/json"})
        with urllib.request.urlopen(req, context=self.ctx) as r:
            raw = r.read()
            return json.loads(raw) if raw else None

    def friends(self):
        return self.request("GET", "/chat/v4/friends")["friends"]

    def remove(self, puuid, pid=None):
        # Con algunos amigos (sobre todo de otras regiones) borrar por puuid responde OK pero no
        # tiene efecto; borrar por pid sí funciona. Se usa pid si se conoce.
        self.request("DELETE", "/chat/v4/friends", {"pid": pid} if pid else {"puuid": puuid})


def fmt_ts(ts):
    return dt.datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d") if ts else ""


VALORANT_LOGS = os.path.expandvars(r"%LOCALAPPDATA%\VALORANT\Saved\Logs")


def seen_in_valorant_logs(puuids):
    """PUUIDs que aparecen en los logs locales de VALORANT (presencias, chat de grupo, partidas).
    VALORANT solo guarda logs de los últimos días, así que es una señal de actividad reciente."""
    import glob
    seen = set()
    pending = set(puuids)
    for path in glob.glob(os.path.join(VALORANT_LOGS, "ShooterGame*.log")):
        try:
            txt = open(path, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        found = {p for p in pending if p in txt}
        seen |= found
        pending -= found
    return seen


SEEN = set()
KEPT = set()  # candidatos que el usuario sacó de candidatos.csv o marcó con 'no'


def load_selection(path):
    """Lee candidatos.csv: devuelve (puuids a eliminar, puuids que el usuario conservó)."""
    delete, keep = set(), set()
    with open(path, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            (delete if r["eliminar"].strip().lower() in ("si", "sí", "s", "yes", "y") else keep).add(r["puuid"])
    return delete, keep


def classify(f, args, now):
    """Devuelve 'activo', 'protegido' o 'candidato'."""
    ts = f.get("last_online_ts")
    if f.get("displayGroup") not in (None, "OFFLINE"):
        return "activo"  # está conectado ahora mismo
    if f["puuid"] in SEEN:
        return "activo"  # visto recientemente en VALORANT
    if ts and (now - ts) / 86400e3 < args.days:
        return "activo"
    if not ts and args.no_null:
        return "activo"
    if (args.keep_notes and f.get("note")) or f.get("group") in args.keep_group:
        return "protegido"
    if f["puuid"] in KEPT:
        return "conservado"
    return "candidato"


def select(friends, args):
    now = time.time() * 1000
    return [f for f in friends if classify(f, args, now) == "candidato"]


def write_dashboard(friends, args, path):
    now = time.time() * 1000
    rows = [{
        "id": f"{f.get('game_name')}#{f.get('game_tag')}",
        "ts": f.get("last_online_ts"),
        "online": f.get("displayGroup") not in (None, "OFFLINE"),
        "group": f.get("group"),
        "region": f.get("region"),
        "note": f.get("note") or "",
        "puuid": f["puuid"],
        "seen": f["puuid"] in SEEN,
        "status": classify(f, args, now),
    } for f in friends]
    tpl = open(os.path.join(HERE, "dashboard_template.html"), encoding="utf-8").read()
    data = json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")
    html = tpl.replace("__DATA__", data).replace("__GENERATED__", dt.datetime.now().strftime("%Y-%m-%d %H:%M"))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # nombres con caracteres no latinos
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    p.add_argument("--days", type=int, default=365)
    p.add_argument("--keep-notes", action="store_true")
    p.add_argument("--keep-group", action="append", default=[])
    p.add_argument("--no-null", action="store_true")
    p.add_argument("--csv", help="CSV a usar con --apply (por defecto candidatos.csv)")
    p.add_argument("--reset", action="store_true", help="ignora la selección guardada en candidatos.csv")
    args = p.parse_args()

    rc = RiotClient()
    friends = rc.friends()
    SEEN.update(seen_in_valorant_logs(f["puuid"] for f in friends if not f.get("last_online_ts")))

    if not args.apply:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        with open(os.path.join(BACKUP_DIR, f"amigos-{stamp}.json"), "w", encoding="utf-8") as fh:
            json.dump(friends, fh, ensure_ascii=False, indent=1)
        if os.path.exists(CSV_PATH) and not args.reset:
            # Respeta la selección del usuario: quien no esté marcado 'si' en el CSV se conserva.
            delete, _ = load_selection(CSV_PATH)
            now = time.time() * 1000
            KEPT.update(f["puuid"] for f in friends
                        if classify(f, args, now) == "candidato" and f["puuid"] not in delete)
        cands = select(friends, args)
        with open(CSV_PATH, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(["eliminar", "riot_id", "ultima_conexion", "grupo", "region", "nota", "puuid"])
            for f in sorted(cands, key=lambda f: f.get("last_online_ts") or 0):
                w.writerow(["si", f"{f.get('game_name')}#{f.get('game_tag')}",
                            fmt_ts(f.get("last_online_ts")) or "sin dato",
                            f.get("group"), f.get("region"), f.get("note") or "", f["puuid"]])
        dash = os.path.join(HERE, "dashboard.html")
        write_dashboard(friends, args, dash)
        print(f"Amigos totales: {len(friends)}  |  candidatos: {len(cands)}")
        print(f"Dashboard: {dash}")
        print(f"Revisa {CSV_PATH} (pon 'no' en la columna 'eliminar' para conservar a alguien)")
        print("Luego ejecuta con --apply para eliminar (o --apply --csv <archivo exportado del dashboard>).")
        return

    csv_path = args.csv or CSV_PATH
    if not os.path.exists(csv_path):
        sys.exit("Primero ejecuta sin --apply para generar candidatos.csv")
    with open(csv_path, encoding="utf-8-sig") as fh:
        rows = [r for r in csv.DictReader(fh) if r["eliminar"].strip().lower() in ("si", "sí", "s", "yes", "y")]
    current = {f["puuid"]: f.get("pid") for f in rc.friends()}
    rows = [r for r in rows if r["puuid"] in current]
    print(f"Eliminando {len(rows)} amigos...")
    ok = 0
    for i, r in enumerate(rows, 1):
        try:
            rc.remove(r["puuid"], current[r["puuid"]])
            ok += 1
            print(f"[{i}/{len(rows)}] eliminado {r['riot_id']}")
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(rows)}] ERROR con {r['riot_id']}: {e}")
        time.sleep(0.3)
    print(f"Listo: {ok} eliminados. Amigos restantes: {len(rc.friends())}")


if __name__ == "__main__":
    main()
