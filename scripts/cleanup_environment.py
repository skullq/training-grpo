import subprocess
import sys
import shutil
from pathlib import Path

def run_cmd(cmd, timeout=10):
    try:
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return res.returncode, res.stdout.strip(), res.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "Timeout expired"
    except Exception as e:
        return -1, "", str(e)

print("=== [1] Containerlab & Docker Resources Cleanup ===")
# 1. clab destroy
code, out, err = run_cmd("clab destroy -t labs/iol-8labs-24sw.clab.yml --cleanup", timeout=15)
print(f"clab destroy (iol-8labs): code={code}, out={out[:100]}, err={err[:100]}")

code, out, err = run_cmd("clab destroy -t labs/iol-multitier-integration.clab.yml --cleanup", timeout=15)
print(f"clab destroy (multitier): code={code}, out={out[:100]}, err={err[:100]}")

# 2. clab inspect
code, out, err = run_cmd("clab inspect --all", timeout=10)
print(f"clab inspect: {out or err}")

# 3. docker ps -a
code, out, err = run_cmd("docker ps -a --filter 'name=clab' --format '{{.Names}}'", timeout=10)
if out:
    print(f"Removing remaining clab containers: {out}")
    run_cmd(f"docker rm -f {out.replace(chr(10), ' ')}", timeout=10)
else:
    print("No clab containers found.")

# 4. Remove clab topology directories if any
for p in Path(".").glob("clab-*"):
    if p.is_dir():
        print(f"Removing directory: {p}")
        shutil.rmtree(p, ignore_errors=True)

for p in Path("/tmp").glob("clab-*"):
    if p.is_dir():
        print(f"Removing /tmp directory: {p}")
        shutil.rmtree(p, ignore_errors=True)

print("=== [2] Cleanup Completed Successfully ===")
