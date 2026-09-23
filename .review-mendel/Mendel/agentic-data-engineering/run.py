#!/usr/bin/env python3
"""
Mendel — one-command launcher.

Bas ye chala:  python run.py

Kya karta hai:
  1. .env na ho to .env.example se bana deta hai
  2. Docker check karta hai; Docker Desktop band hai to khud start karke ready hone tak wait karta hai
  3. `docker compose up --build` chala ke Postgres + app dono khada karta hai
  4. App ready hote hi browser me http://localhost:8080 khol deta hai
  5. Docker na ho to Maven (mvn spring-boot:run) fallback try karta hai

Options:
  python run.py           # normal run (Docker preferred)
  python run.py --local   # Docker skip, seedha Maven se chala (apna Postgres chahiye)
  python run.py --down    # sab band karo (docker compose down)
"""
import os
import sys
import time
import shutil
import platform
import subprocess
import threading
import urllib.request

URL = "http://localhost:8080"
IS_WIN = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"


# ---------- pretty printing ----------
def say(msg):   print("\n\033[1;36m» \033[0m" + msg)
def ok(msg):    print("\033[1;32m✓ \033[0m" + msg)
def warn(msg):  print("\033[1;33m! \033[0m" + msg)
def err(msg):   print("\033[1;31m✗ \033[0m" + msg)
def banner():
    print("\033[1;32m")
    print("  ███  MENDEL  —  Agentic Data Engineering")
    print("  Ek command me pura project chala rahe hain...\033[0m")


def have(cmd):
    return shutil.which(cmd) is not None


def project_root():
    """Folder jisme docker-compose.yml / pom.xml ho. Script ke paas hi hona chahiye."""
    here = os.path.dirname(os.path.abspath(__file__))
    for base in (here, os.getcwd()):
        if os.path.exists(os.path.join(base, "docker-compose.yml")) or \
           os.path.exists(os.path.join(base, "pom.xml")):
            return base
    return here


# ---------- docker helpers ----------
def compose_cmd():
    """`docker compose` (v2) ya `docker-compose` (v1) — jo mile."""
    try:
        subprocess.run(["docker", "compose", "version"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return ["docker", "compose"]
    except Exception:
        if have("docker-compose"):
            return ["docker-compose"]
    return None


def docker_running():
    try:
        subprocess.run(["docker", "info"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       check=True, timeout=15)
        return True
    except Exception:
        return False


def start_docker_desktop():
    say("Docker Desktop start kar raha hoon...")
    try:
        if IS_WIN:
            for p in (r"C:\Program Files\Docker\Docker\Docker Desktop.exe",
                      os.path.expandvars(r"%ProgramFiles%\Docker\Docker\Docker Desktop.exe")):
                if os.path.exists(p):
                    os.startfile(p)  # type: ignore[attr-defined]
                    return True
            subprocess.Popen(["cmd", "/c", "start", "", "Docker Desktop"])
            return True
        elif IS_MAC:
            subprocess.Popen(["open", "-a", "Docker"])
            return True
        else:  # Linux
            for c in (["systemctl", "--user", "start", "docker-desktop"],
                      ["systemctl", "start", "docker"]):
                try:
                    subprocess.run(c, check=True); return True
                except Exception:
                    continue
    except Exception as e:
        warn("Docker Desktop auto-start nahi ho paya: %s" % e)
    return False


def wait_for_docker(timeout=180):
    say("Docker engine ke ready hone ka wait (max %ds)..." % timeout)
    start = time.time()
    while time.time() - start < timeout:
        if docker_running():
            ok("Docker engine ready.")
            return True
        print("   ...abhi start ho raha hai", end="\r")
        time.sleep(3)
    return False


# ---------- browser opener ----------
def open_when_ready():
    for _ in range(150):  # ~5 min
        try:
            urllib.request.urlopen(URL, timeout=2)
            ok("App ready! Browser khol raha hoon: " + URL)
            try:
                import webbrowser
                webbrowser.open(URL)
            except Exception:
                pass
            return
        except Exception:
            time.sleep(2)


# ---------- env ----------
def ensure_env(root):
    envf = os.path.join(root, ".env")
    example = os.path.join(root, ".env.example")
    if not os.path.exists(envf) and os.path.exists(example):
        shutil.copyfile(example, envf)
        ok(".env bana diya (.env.example se). Gemini key chahiye to usme daal dena — optional hai.")


# ---------- run paths ----------
def run_docker(root):
    cc = compose_cmd()
    if cc is None:
        err("Docker mila par `compose` nahi. Docker Desktop update kar (compose v2 aata hai usme).")
        return 1

    if not docker_running():
        if not start_docker_desktop() or not wait_for_docker():
            err("Docker engine start nahi hua. Docker Desktop khud open karke (whale icon green) dobara `python run.py` chala.")
            return 1

    threading.Thread(target=open_when_ready, daemon=True).start()
    say("Build + run ho raha hai (pehli baar 3–5 min lag sakte hain)...")
    print("   Band karne ke liye is terminal me Ctrl+C dabana.\n")
    try:
        subprocess.run(cc + ["up", "--build"], cwd=root)
    except KeyboardInterrupt:
        pass
    finally:
        say("Containers band kar raha hoon...")
        subprocess.run(cc + ["down"], cwd=root)
    return 0


def run_local(root):
    say("Local mode (bina Docker) — Java 21 + Maven + chalu Postgres chahiye.")
    if not (have("java") and (have("mvn") or os.path.exists(os.path.join(root, "mvnw")))):
        err("Java ya Maven nahi mila. Sabse aasan rasta: Docker Desktop install karke bina --local ke chala.")
        return 1
    warn("Dhyan: Postgres localhost:5432 pe chalu hona chahiye — database 'ade', user 'ade', password 'ade'.")
    env = dict(os.environ)
    env.setdefault("POSTGRES_HOST", "localhost")
    env.setdefault("POSTGRES_USER", "ade")
    env.setdefault("POSTGRES_PASSWORD", "ade")
    env.setdefault("POSTGRES_DB", "ade")
    mvn = os.path.join(root, "mvnw") if os.path.exists(os.path.join(root, "mvnw")) and not IS_WIN else "mvn"
    threading.Thread(target=open_when_ready, daemon=True).start()
    try:
        subprocess.run([mvn, "spring-boot:run"], cwd=root, env=env)
    except KeyboardInterrupt:
        pass
    return 0


def main():
    banner()
    root = project_root()
    if not (os.path.exists(os.path.join(root, "docker-compose.yml")) or
            os.path.exists(os.path.join(root, "pom.xml"))):
        err("Project files nahi mile. run.py ko 'agentic-data-engineering' folder ke andar rakh "
            "(jahan docker-compose.yml aur pom.xml hain), phir chala.")
        return 1
    os.chdir(root)
    ok("Project folder: " + root)

    args = sys.argv[1:]
    cc = compose_cmd()

    if "--down" in args:
        if cc:
            subprocess.run(cc + ["down"], cwd=root)
            ok("Sab band. 👍")
        return 0

    ensure_env(root)

    if "--local" in args:
        return run_local(root)

    if have("docker") and cc:
        return run_docker(root)

    warn("Docker nahi mila. Local (Maven) se try kar raha hoon...")
    return run_local(root)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nRuk gaya. 👋")
