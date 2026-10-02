import json
import os
import re
from typing import List, Optional, Set


class TeamAdvisor:
    """Rexlent-guided Team Advisor and Roster Evaluator for Wuthering Waves.

    Evaluates unlocked characters against Rexlent's meta synergy matrices and
    recommends/constructs optimal 3-character team slot assignments.
    """

    DEFAULT_CONFIG_PATH = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "configs",
        "rexlent_teams.json"
    )

    # Name normalization mapping to canonical keys.
    # Covers repo label names, alternate skin templates, Prydwen (EN) spellings
    # and the CN romanizations used by the recognition templates.
    ALIAS_MAP = {
        # Spectro
        "jinhsi": "char_jinhsi", "jinshi": "char_jinhsi", "char_jinhsi2": "char_jinhsi",
        "verina": "char_verina",
        "shorekeeper": "char_shorekeeper", "shore keeper": "char_shorekeeper",
        "shore_keeper": "char_shorekeeper", "the shorekeeper": "char_shorekeeper",
        "phoebe": "char_phoebe",
        "zani": "char_zani", "char_zani2": "char_zani",
        "lucy": "char_lucy",
        "lynae": "char_linnai", "linnai": "char_linnai", "char_linnai2": "char_linnai",
        "luuk herssen": "char_luhesi", "luukherssen": "char_luhesi", "luhesi": "char_luhesi",
        # Electro
        "yinlin": "char_yinlin",
        "xiangliyao": "char_xiangliyao", "xiangli yao": "char_xiangliyao", "xiangli_yao": "char_xiangliyao",
        "calcharo": "char_calcharo",
        "yuanwu": "char_yuanwu",
        "lumi": "char_lumi",
        "augusta": "char_augusta",
        "rebecca": "char_rebecca",
        "buling": "char_douling", "douling": "char_douling",
        "hsin": "char_hsin",
        "suoming": "char_suoming",
        # Fusion
        "changli": "char_changli", "chang_changli": "char_changli", "char_changli2": "char_changli",
        "encore": "char_encore",
        "mortefi": "char_mortefi",
        "chixia": "char_chixia",
        "brant": "char_brant",
        "lupa": "char_lupa",
        "galbrena": "char_galbrena",
        "denia": "char_denia",
        "aemeath": "char_aemeath",
        "mornye": "char_moning", "moning": "char_moning", "char_moning_new": "char_moning",
        "jingran": "char_jingran",
        # Glacio
        "carlotta": "char_carlotta", "char_carlotta2": "char_carlotta",
        "zhezhi": "char_zhezhi",
        "sanhua": "char_sanhua", "char_sanhua2": "char_sanhua",
        "baizhi": "char_baizhi",
        "youhu": "char_youhu",
        "lingyang": "char_lingyang",
        "hiyuki": "char_hiyuki",
        "suisui": "char_suisui",
        "lucilla": "char_lucilla",
        # Havoc
        "camellya": "char_camellya", "chamelia": "char_camellya",
        "danjin": "char_danjin",
        "taoqi": "char_taoqi",
        "roccia": "char_roccia",
        "cantarella": "char_cantarella",
        "phrolova": "char_phrolova",
        "chisa": "char_chisa", "char_chisa2": "char_chisa",
        "yangyang xuanling": "yangyang_sp", "yangyangxuanling": "yangyang_sp",
        "yangyang sp": "yangyang_sp", "yangyangsp": "yangyang_sp",
        # Aero
        "jiyan": "char_jiyan",
        "jianxin": "char_jianxin",
        "yangyang": "char_yangyang",
        "aalto": "char_aalto",
        "cartethyia": "char_cartethyia",
        "ciaccona": "char_ciaccona",
        "iuno": "char_iuno",
        "qingxiao": "char_qingxiao",
        "qiuyuan": "char_chouyuan", "chouyuan": "char_chouyuan",
        "sigrika": "char_xigelika", "xigelika": "char_xigelika",
        # Rover (all forms share one recognition identity)
        "rover": "char_rover", "rover (havoc)": "char_rover", "rover (spectro)": "char_rover",
        "rover (aero)": "char_rover", "rover (electro)": "char_rover",
        "char_rover_male": "char_rover",
    }

    # Tier -> score. Prydwen/Rexlent data uses T0 (best) .. T4 (worst), older
    # revisions of the database used letter tiers, so both are supported.
    TIER_SCORES = {
        "T0": 100, "T0.5": 95, "T1": 90, "T1.5": 85, "T2": 80, "T3": 70, "T4": 60,
        "S+": 100, "S": 90, "A+": 80, "A": 70, "B+": 60, "B": 50,
    }
    DEFAULT_TIER_SCORE = 65

    @classmethod
    def tier_score(cls, tier) -> int:
        """Numeric weight of a tier label, tolerant of unknown/unrated labels."""
        if tier is None:
            return cls.DEFAULT_TIER_SCORE
        key = str(tier).strip()
        if key in cls.TIER_SCORES:
            return cls.TIER_SCORES[key]
        upper = key.upper()
        if upper in cls.TIER_SCORES:
            return cls.TIER_SCORES[upper]
        # e.g. "T1 (3.7)" or "Unrated (3.7, unreleased)"
        match = re.match(r'^T\s*(\d+(?:\.\d+)?)', upper)
        if match:
            normalized = f"T{match.group(1)}"
            if normalized in cls.TIER_SCORES:
                return cls.TIER_SCORES[normalized]
            try:
                return max(40, 100 - int(float(match.group(1)) * 10))
            except ValueError:
                return cls.DEFAULT_TIER_SCORE
        return cls.DEFAULT_TIER_SCORE

    def __init__(self, data_path: Optional[str] = None):
        self.data_path = data_path or self.DEFAULT_CONFIG_PATH
        self.data = self._load_data()
        self.characters = self.data.get("characters", {})
        self.meta_teams = self.data.get("meta_teams", [])

    def _load_data(self) -> dict:
        if os.path.exists(self.data_path):
            with open(self.data_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"characters": {}, "meta_teams": []}

    def normalize_name(self, name: str) -> str:
        """Normalize character identifier into canonical database key."""
        clean = name.strip()
        if clean.lower().startswith("labels."):
            clean = clean[7:]
        lower = clean.lower()
        no_space = lower.replace(" ", "").replace("_", "")
        if lower in self.ALIAS_MAP:
            return self.ALIAS_MAP[lower]
        if no_space in self.ALIAS_MAP:
            return self.ALIAS_MAP[no_space]
        return self.ALIAS_MAP.get(clean, clean)

    def get_character(self, name: str) -> Optional[dict]:
        """Fetch character metadata by name or alias."""
        key = self.normalize_name(name)
        return self.characters.get(key)

    def recommend_teams(
        self,
        unlocked_characters: List[str],
        prefer_main_dps: Optional[str] = None,
        top_n: int = 5
    ) -> List[dict]:
        """Evaluate unlocked roster and return top-ranked Rexlent team compositions.

        Standard slot assignments strictly match Rexlent rotation order:
          - Slot 1: Healer / Team Buffer (Rejuvenating Glow / Bell-Borne or Fallacy)
          - Slot 2: Sub-DPS / Dedicated Buffer (Moonlit Clouds / Heron)
          - Slot 3: Main DPS (Element 5pc / 4-Cost Echo)
        """
        unlocked_set: Set[str] = {self.normalize_name(c) for c in unlocked_characters}
        pref_key = self.normalize_name(prefer_main_dps) if prefer_main_dps else None

        scored_teams = []

        # 1. Evaluate predefined Rexlent meta teams
        for meta in self.meta_teams:
            meta_slots = meta.get("slots", [])
            if len(meta_slots) != 3:
                continue

            healer_spec = meta_slots[0]
            sub_spec = meta_slots[1]
            main_spec = meta_slots[2]

            main_char = main_spec["character"]
            if main_char not in unlocked_set:
                continue

            if pref_key and main_char != pref_key:
                continue

            # Resolve Sub-DPS
            chosen_sub = None
            sub_penalty = 0
            if sub_spec["character"] in unlocked_set:
                chosen_sub = sub_spec["character"]
            else:
                for fb in sub_spec.get("fallback", []):
                    if fb in unlocked_set:
                        chosen_sub = fb
                        sub_penalty = 5
                        break

            if not chosen_sub:
                continue

            # Resolve Healer
            chosen_healer = None
            healer_penalty = 0
            if healer_spec["character"] in unlocked_set:
                chosen_healer = healer_spec["character"]
            else:
                for fb in healer_spec.get("fallback", []):
                    if fb in unlocked_set:
                        chosen_healer = fb
                        healer_penalty = 5
                        break

            if not chosen_healer:
                continue

            # Calculate base score from tier
            base_score = self.tier_score(meta.get("tier"))
            final_score = base_score - sub_penalty - healer_penalty

            healer_info = self.get_character(chosen_healer) or {}
            sub_info = self.get_character(chosen_sub) or {}
            main_info = self.get_character(main_char) or {}

            team_obj = {
                "name": meta.get("name", "Custom Team"),
                "tier": meta.get("tier", "A"),
                "score": final_score,
                "guide_url": meta.get("guide_url", ""),
                "synergy_summary": meta.get("synergy_summary", ""),
                "slots": [
                    {
                        "slot": 1,
                        "role": "Healer",
                        "character": chosen_healer,
                        "display_name": healer_info.get("display_name", chosen_healer),
                        "echo_set": healer_spec.get("echo_set", healer_info.get("best_echo_set", "")),
                        "main_echo": healer_spec.get("main_echo", healer_info.get("main_echo", ""))
                    },
                    {
                        "slot": 2,
                        "role": "SubDPS",
                        "character": chosen_sub,
                        "display_name": sub_info.get("display_name", chosen_sub),
                        "echo_set": sub_spec.get("echo_set", sub_info.get("best_echo_set", "")),
                        "main_echo": sub_spec.get("main_echo", sub_info.get("main_echo", ""))
                    },
                    {
                        "slot": 3,
                        "role": "MainDPS",
                        "character": main_char,
                        "display_name": main_info.get("display_name", main_char),
                        "echo_set": main_spec.get("echo_set", main_info.get("best_echo_set", "")),
                        "main_echo": main_spec.get("main_echo", main_info.get("main_echo", ""))
                    }
                ]
            }
            scored_teams.append(team_obj)

        # 2. If no meta teams match, synthesize dynamic team via Rexlent synergy rules
        if not scored_teams:
            dynamic_team = self._synthesize_team(unlocked_set, pref_key)
            if dynamic_team:
                scored_teams.append(dynamic_team)

        # Sort by score descending
        scored_teams.sort(key=lambda t: t.get("score", 0), reverse=True)
        return scored_teams[:top_n]

    def _synthesize_team(self, unlocked: Set[str], prefer_dps: Optional[str] = None) -> Optional[dict]:
        """Synthesize a synergized team dynamically when no predefined template fits."""
        available_chars = [self.characters[c] for c in unlocked if c in self.characters]
        if not available_chars:
            return None

        # Filter by roles
        main_dps_list = [c for c in available_chars if c.get("role") == "MainDPS"]
        sub_dps_list = [c for c in available_chars if c.get("role") == "SubDPS"]
        healer_list = [c for c in available_chars if c.get("role") == "Healer"]

        # Default fallbacks if strict roles not present
        if not healer_list:
            healer_list = [c for c in available_chars if "healer" in c.get("synergies", [])]
        if not sub_dps_list:
            sub_dps_list = [c for c in available_chars if c not in healer_list and c not in main_dps_list]
        if not main_dps_list:
            main_dps_list = [c for c in available_chars if c not in healer_list]
        if not healer_list:
            # No dedicated healer/support in the roster: fall back to any character
            # that is not needed as the Main DPS so a 3-slot team can still be built.
            healer_list = [c for c in available_chars if c not in main_dps_list] or available_chars

        if not main_dps_list:
            return None

        # Pick Main DPS
        if prefer_dps and prefer_dps in self.characters and prefer_dps in unlocked:
            dps_char = self.characters[prefer_dps]
        else:
            main_dps_list.sort(key=lambda c: self.tier_score(c.get("tier")), reverse=True)
            dps_char = main_dps_list[0]

        # Pick Healer (Verina > Shorekeeper > Baizhi)
        healer_priority = ["char_verina", "char_shorekeeper", "char_baizhi", "char_jianxin", "char_youhu", "char_taoqi"]
        healer_char = None
        for hp in healer_priority:
            if hp in unlocked:
                healer_char = self.characters[hp]
                break
        if not healer_char and healer_list:
            healer_char = healer_list[0]

        # Pick Sub-DPS with synergy
        sub_char = None
        dps_synergies = set(dps_char.get("synergies", []))
        for candidate in sub_dps_list:
            cand_key = self.normalize_name(candidate["display_name"])
            if cand_key in dps_synergies and candidate != healer_char and candidate != dps_char:
                sub_char = candidate
                break

        if not sub_char:
            for candidate in available_chars:
                if candidate != healer_char and candidate != dps_char:
                    sub_char = candidate
                    break

        if not (dps_char and healer_char and sub_char):
            return None

        dps_key = self.normalize_name(dps_char["display_name"])
        sub_key = self.normalize_name(sub_char["display_name"])
        healer_key = self.normalize_name(healer_char["display_name"])

        return {
            "name": f"{dps_char['display_name']} Dynamic Synergy Team",
            "tier": dps_char.get("tier", "A"),
            "score": 75,
            "synergy_summary": f"{sub_char['display_name']} supports {dps_char['display_name']} with {healer_char['display_name']} healing.",
            "slots": [
                {
                    "slot": 1,
                    "role": "Healer",
                    "character": healer_key,
                    "display_name": healer_char.get("display_name", healer_key),
                    "echo_set": healer_char.get("best_echo_set", "Rejuvenating Glow (5pc)"),
                    "main_echo": healer_char.get("main_echo", "Bell-Borne Geochelone")
                },
                {
                    "slot": 2,
                    "role": "SubDPS",
                    "character": sub_key,
                    "display_name": sub_char.get("display_name", sub_key),
                    "echo_set": sub_char.get("best_echo_set", "Moonlit Clouds (5pc)"),
                    "main_echo": sub_char.get("main_echo", "Impermanence Heron")
                },
                {
                    "slot": 3,
                    "role": "MainDPS",
                    "character": dps_key,
                    "display_name": dps_char.get("display_name", dps_key),
                    "echo_set": dps_char.get("best_echo_set", ""),
                    "main_echo": dps_char.get("main_echo", "")
                }
            ]
        }

    def format_team_display(self, team: dict) -> str:
        """Format team recommendation into human-readable summary."""
        lines = []
        lines.append(f"Team: {team.get('name')} [Tier: {team.get('tier')}] (Score: {team.get('score')})")
        if team.get("synergy_summary"):
            lines.append(f"Synergy: {team.get('synergy_summary')}")
        if team.get("guide_url"):
            lines.append(f"Rexlent Guide: {team.get('guide_url')}")
        lines.append("Party Slots:")
        for s in team.get("slots", []):
            lines.append(
                f"  Slot {s['slot']} [{s['role']}]: {s['display_name']} | Echo: {s.get('echo_set')} ({s.get('main_echo')})"
            )
        return "\n".join(lines)
