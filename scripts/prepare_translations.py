#!/usr/bin/env python3
"""
Prepare translations for the OMVA voice enrollment skill.
This script should run every time the contents of the locale folder change.
"""

import json
from os.path import dirname
import os


def prepare_translations():
    """Extract all locale strings into JSON format for translation"""
    locale = f"{dirname(dirname(__file__))}/locale"
    tx = f"{dirname(dirname(__file__))}/translations"
    
    print("Preparing translations from locale files...")

    for lang in os.listdir(locale):
        if not os.path.isdir(f"{locale}/{lang}"):
            continue
            
        print(f"Processing language: {lang}")
        
        intents = {}
        dialogs = {}
        entities = {}
        
        for root, _, files in os.walk(f"{locale}/{lang}"):
            b = root.split(f"/{lang}")[-1]

            for f in files:
                if b:
                    fid = f"{b}/{f}"
                else:
                    fid = f
                    
                try:
                    with open(f"{root}/{f}", encoding='utf-8') as fi:
                        strings = [l.replace("{{", "{").replace("}}", "}")
                                   for l in fi.read().split("\n") if l.strip()
                                   and not l.startswith("#")]

                    if fid.endswith(".intent"):
                        intents[fid] = strings
                    elif fid.endswith(".dialog"):
                        dialogs[fid] = strings
                    elif fid.endswith(".entity"):
                        entities[fid] = strings
                except Exception as e:
                    print(f"Error processing {f}: {e}")

        # Create translations directory
        os.makedirs(f"{tx}/{lang}", exist_ok=True)
        
        if intents:
            with open(f"{tx}/{lang}/intents.json", "w", encoding='utf-8') as f:
                json.dump(intents, f, indent=4, ensure_ascii=False)
                
        if dialogs:
            with open(f"{tx}/{lang}/dialogs.json", "w", encoding='utf-8') as f:
                json.dump(dialogs, f, indent=4, ensure_ascii=False)
                
        if entities:
            with open(f"{tx}/{lang}/entities.json", "w", encoding='utf-8') as f:
                json.dump(entities, f, indent=4, ensure_ascii=False)
        
        print(f"Translations prepared for {lang}: {len(intents)} intents, {len(dialogs)} dialogs, {len(entities)} entities")

    print("Translation preparation complete!")


if __name__ == "__main__":
    prepare_translations()