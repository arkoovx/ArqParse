import os
import re

RESULTS_DIR = "/tmp/test_results"

def merge():
    out_file = os.path.join(RESULTS_DIR, "all_top_vpn.txt")
    os.makedirs(RESULTS_DIR, exist_ok=True)
    current_sections = {}
    if os.path.exists(out_file):
        with open(out_file, 'r', encoding='utf-8') as f:
            current_section = "General"
            for line in f:
                line = line.strip()
                if line.startswith("# SECTION:"):
                    current_section = line.replace("# SECTION:", "").strip()
                    current_sections.setdefault(current_section, [])
                elif line and not line.startswith('#'):
                    current_sections.setdefault(current_section, []).append(line)

    sources = {"Base VPN": "top_base_vpn.txt", "Bypass VPN": "top_bypass_vpn.txt"}
    updated_sections = {}
    for name, fn in sources.items():
        fp = os.path.join(RESULTS_DIR, fn)
        if os.path.exists(fp):
            with open(fp, 'r', encoding='utf-8') as f:
                cfgs = [l.strip() for l in f if l.strip() and not l.startswith('#')]
            if cfgs:
                updated_sections[name] = cfgs

    for name, cfgs in updated_sections.items():
        current_sections[name] = cfgs

    with open(out_file, 'w', encoding='utf-8') as f:
        f.write("#profile-update-interval: 48\n\n")
        ordered_sections = ["Base VPN", "Bypass VPN"]
        for name in ordered_sections:
            if name in current_sections:
                f.write(f"\n# SECTION: {name}\n")
                for c in current_sections[name]:
                    f.write(f"{c}\n")

if __name__ == "__main__":
    merge()
