"""Fetch a build: config.xml, params.json, pipeline.groovy, pipeline.log.

Ported from fetch-build.sh / jenkins-common.sh, with the same output files.
"""

from __future__ import annotations

import html
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote

from .api import Jenkins, JenkinsError


# ─── URL helpers ────────────────────────────────────────────────────────────

def split_url(path: str) -> tuple[str, int | None]:
    """'/job/A/job/B/513' -> ('/job/A/job/B', 513); job URL -> (job, None)."""
    path = re.sub(r"/(lastBuild|replay.*)$", "", path.rstrip("/"))
    m = re.match(r"^(.*)/(\d+)$", path)
    if m:
        return m.group(1), int(m.group(2))
    return path, None


def dir_name(job_path: str, number: int) -> str:
    names = re.findall(r"/job/([^/]+)", job_path)
    name = unquote(names[-1] if names else "build").lower().replace(" ", "-")
    return f"{name}-{number}"


# ─── build resolution ───────────────────────────────────────────────────────

def latest(jk: Jenkins, job: str) -> tuple[int, str]:
    d = jk.json(f"{job}/lastBuild", tree="number,result")
    return d["number"], d.get("result") or "IN_PROGRESS"


def latest_not_aborted(jk: Jenkins, job: str, lookback: int = 20, log=print) -> tuple[int, str]:
    builds = jk.json(job, tree=f"builds[number,result]{{0,{lookback}}}").get("builds", [])
    if not builds:
        raise JenkinsError("no builds found")
    for b in builds:
        result = b.get("result") or "IN_PROGRESS"
        if result == "ABORTED":
            log(f"  #{b['number']}: ABORTED (skipping)")
            continue
        return b["number"], result
    raise JenkinsError(f"all of the last {len(builds)} builds were ABORTED")


# ─── config.xml ─────────────────────────────────────────────────────────────

def fetch_config(jk: Jenkins, job: str, out: Path, log=print) -> str | None:
    log("Fetching job config...")
    try:
        raw = jk.text(f"{job}/config.xml")
    except JenkinsError as exc:
        log(f"  WARN: could not fetch config.xml ({exc})")
        return None
    if "<html" in raw[:200].lower():
        log("  WARN: could not fetch config.xml (got an HTML page - permissions?)")
        return None
    dest = out / "config.xml"
    dest.write_text(raw)
    try:
        root = ET.fromstring(raw)
        log("  Status: " + ("DISABLED" if root.findtext("disabled", "false") == "true" else "enabled"))
        defn = root.find(".//definition")
        if defn is not None:
            cls = defn.get("class", "")
            if "CpsScmFlowDefinition" in cls:
                log("  Pipeline: SCM")
                scm = defn.findtext(".//userRemoteConfigs/hudson.plugins.git.UserRemoteConfig/url")
                branch = defn.findtext(".//branches/hudson.plugins.git.BranchSpec/name")
                if scm:
                    log(f"    Repo: {scm}")
                if branch:
                    log(f"    Branch: {branch}")
                log(f"    Script: {defn.findtext('scriptPath', 'Jenkinsfile')}")
            elif "CpsFlowDefinition" in cls:
                log("  Pipeline: Inline (script in job config)")
            else:
                log(f"  Pipeline: {cls}")
        triggers = root.findall(".//triggers/*")
        if triggers:
            log(f"  Triggers: {len(triggers)}")
            for t in triggers:
                spec = t.findtext("spec", "")
                log(f"    {t.tag.split('.')[-1]}" + (f": {spec}" if spec else ""))
    except ET.ParseError as exc:
        log(f"  (saved raw XML, could not parse: {exc})")
    log(f"  -> {dest}")
    return raw


# ─── params.json ────────────────────────────────────────────────────────────

def _xml_param_defs(config_raw: str | None) -> dict:
    defs = {}
    if not config_raw:
        return defs
    try:
        root = ET.fromstring(config_raw)
    except ET.ParseError:
        return defs
    for pd in root.findall(".//parameterDefinitions/*"):
        name = pd.findtext("name", "")
        if not name:
            continue
        tag = pd.tag.split(".")[-1]
        entry = {"type": tag}
        desc = pd.findtext("description", "")
        if desc:
            entry["description"] = desc
        dv = pd.find("defaultValue")
        if dv is not None and dv.text is not None:
            entry["default"] = dv.text
        choices = [s.text for s in pd.findall(".//string") if s.text]
        if choices:
            entry["choices"] = choices
            entry.setdefault("default", choices[0])
        if "Boolean" in tag:
            entry["default"] = pd.findtext("defaultValue", "false")
        defs[name] = entry
    return defs


def fetch_params(jk: Jenkins, job: str, build: str, config_raw: str | None, out: Path, log=print) -> dict:
    log("Fetching parameters...")
    # 1. what the build actually ran with
    build_data = jk.json(build, tree="number,result,actions[parameters[name,value]]")
    build_params = {}
    for action in build_data.get("actions", []) or []:
        for p in (action or {}).get("parameters", []) or []:
            build_params[p["name"]] = p.get("value")

    # 2. job-level definitions from the API
    api_defs = {}
    try:
        job_data = jk.json(job, tree="property[parameterDefinitions[name,type,defaultParameterValue[value],"
                                     "description,choices]]")
        for prop in job_data.get("property", []) or []:
            for pd in (prop or {}).get("parameterDefinitions", []) or []:
                api_defs[pd["name"]] = pd
    except JenkinsError:
        pass

    # 3. config.xml definitions (base), API enriches, build gives the values
    xml_defs = _xml_param_defs(config_raw)
    all_defs = {n: dict(d) for n, d in xml_defs.items()}
    for name, d in api_defs.items():
        ad = all_defs.setdefault(name, {})
        if d.get("type"):
            ad["type"] = d["type"]
        dv = d.get("defaultParameterValue") or {}
        if dv.get("value") is not None:
            ad.setdefault("default", dv["value"])
        if d.get("description"):
            ad.setdefault("description", d["description"])
        if d.get("choices"):
            ad.setdefault("choices", d["choices"])

    merged = []
    for name in dict.fromkeys(list(all_defs) + list(build_params)):
        defn = all_defs.get(name, {})
        entry = {"name": name}
        for key in ("type", "default", "description", "choices"):
            if defn.get(key) is not None:
                entry[key] = defn[key]
        if name in build_params:
            entry["value"], entry["source"] = build_params[name], "build"
        elif "default" in entry:
            entry["value"], entry["source"] = entry["default"], "default"
        merged.append(entry)

    output = {"number": build_data.get("number"), "result": build_data.get("result"), "parameters": merged}
    (out / "params.json").write_text(json.dumps(output, indent=2))

    log(f"  Result: {output['result'] or 'IN_PROGRESS'}")
    if merged:
        log(f"  Parameters ({len(merged)}):")
        for p in merged:
            ptype = f" [{p['type']}]" if p.get("type") else ""
            src = f" ({p['source']})" if p.get("source") else ""
            log(f"    {p['name']}: {p.get('value', '(none)')}{ptype}{src}")
    else:
        log("  No parameters")
    return output


# ─── Jenkinsfile + log ──────────────────────────────────────────────────────

def jenkinsfile_text(jk: Jenkins, build: str) -> str | None:
    """The script a build ran, read from its replay page (GET only; nothing is replayed)."""
    page = jk.text(f"{build}/replay/")
    m = re.search(r'<textarea[^>]*name="_\.mainScript"[^>]*>(.*?)</textarea>', page, re.S)
    if not m or not m.group(1).strip():
        return None
    return html.unescape(m.group(1))


def fetch_jenkinsfile(jk: Jenkins, build: str, out: Path, log=print) -> bool:
    log("Fetching Jenkinsfile...")
    try:
        script = jenkinsfile_text(jk, build)
    except JenkinsError as exc:
        log(f"  Could not extract Jenkinsfile ({exc})")
        return False
    if script is None:
        log("  Could not extract Jenkinsfile (no replay script - permissions or not a pipeline)")
        return False
    dest = out / "pipeline.groovy"
    dest.write_text(script)
    log(f"  {script.count(chr(10)) + 1} lines -> {dest}")
    return True


def fetch_log(jk: Jenkins, build: str, out: Path, log=print) -> None:
    log("Fetching console log...")
    dest = out / "pipeline.log"
    size = jk.download(f"{build}/consoleText", dest)
    with open(dest, "rb") as fh:
        lines = sum(1 for _ in fh)
    log(f"  {size} bytes, {lines} lines -> {dest}")


# ─── all four files ─────────────────────────────────────────────────────────

def save_build(jk: Jenkins, base_url: str, job: str, number: int, out: Path, log=print) -> None:
    """What `jenkins fetch` saves: config.xml, params.json, pipeline.groovy, pipeline.log."""
    build = f"{job}/{number}"
    out.mkdir(parents=True, exist_ok=True)
    log("")
    log(f"Build:  {base_url.rstrip('/')}{build}")
    log(f"Output: {out}/")
    log("")
    config_raw = fetch_config(jk, job, out, log=log)
    log("")
    fetch_params(jk, job, build, config_raw, out, log=log)
    log("")
    fetch_jenkinsfile(jk, build, out, log=log)
    log("")
    fetch_log(jk, build, out, log=log)
    log("")
    log(f"Done. All files in {out}/")
