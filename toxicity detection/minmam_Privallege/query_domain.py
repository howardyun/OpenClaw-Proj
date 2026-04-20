from __future__ import annotations

import argparse
import json
import re
from typing import Any, Dict, List, Optional

from core import load_domains_from_yaml, sort_atoms


class DomainQueryService:
    def __init__(self, yaml_path: str):
        self.domains = load_domains_from_yaml(yaml_path)
        self._by_id = {self._normalize_key(domain.id): domain for domain in self.domains}
        self._by_name = {self._normalize_key(domain.name): domain for domain in self.domains}

    @staticmethod
    def _normalize_key(text: str) -> str:
        return re.sub(r"\s+", "", text).lower()

    def find_domain(self, domain_key: str):
        key = self._normalize_key(domain_key)
        if key in self._by_id:
            return self._by_id[key]
        if key in self._by_name:
            return self._by_name[key]

        candidates = [
            domain
            for domain in self.domains
            if key in self._normalize_key(domain.id) or key in self._normalize_key(domain.name)
        ]
        if not candidates:
            raise KeyError(f"未找到功能域: {domain_key}")
        if len(candidates) > 1:
            names = ", ".join(f"{domain.id}:{domain.name}" for domain in candidates)
            raise KeyError(f"功能域不唯一，请更精确指定: {names}")
        return candidates[0]

    def _resolve_combination(
        self,
        domain_key: str,
        *,
        base_domain: Optional[str] = None,
        target_action_atom: Optional[str] = None,
    ) -> Dict[str, Any]:
        domain = self.find_domain(domain_key)
        combo = domain.minimum_permission_combinations

        result: Dict[str, Any] = {
            "raw": combo.raw,
            "all_of": list(combo.all_of),
            "one_of": [list(group) for group in combo.one_of],
            "refs": list(combo.refs),
            "placeholders": [dict(item) for item in combo.placeholders],
        }

        if "base_domain_minimum_permission_set" in result["refs"]:
            if not base_domain:
                raise ValueError(f"{domain.id}:{domain.name} 需要提供 --base-domain 才能解析组合模板。")
            base = self.find_domain(base_domain)
            result["all_of"] = sort_atoms(base.minimum_permission_set.atoms + result["all_of"])
            result["resolved_from_base_domain"] = {
                "domain_id": base.id,
                "domain_name": base.name,
                "minimum_permission_set": base.minimum_permission_set.atoms,
            }

        for placeholder in result["placeholders"]:
            if placeholder.get("name") == "target_action_atom":
                placeholder["resolved_to"] = target_action_atom
                if target_action_atom:
                    result["all_of"] = sort_atoms(result["all_of"] + [target_action_atom])

        result["all_of"] = sort_atoms(result["all_of"])
        result["one_of"] = [sort_atoms(group) for group in result["one_of"]]
        return result

    def get_domain_info(
        self,
        domain_key: str,
        *,
        base_domain: Optional[str] = None,
        target_action_atom: Optional[str] = None,
    ) -> Dict[str, Any]:
        domain = self.find_domain(domain_key)
        return {
            "domain_id": domain.id,
            "domain_name": domain.name,
            "examples": domain.examples,
            "max_tier_whitelist": domain.max_tier_whitelist,
            "minimum_permission_set": {
                "raw": domain.minimum_permission_set.raw,
                "atoms": domain.minimum_permission_set.atoms,
            },
            "minimum_permission_combinations": self._resolve_combination(
                domain_key,
                base_domain=base_domain,
                target_action_atom=target_action_atom,
            ),
            "forbidden_atoms": {
                "raw": domain.forbidden_atoms.raw,
                "atoms": domain.forbidden_atoms.atoms,
            },
            "out_of_scope_atoms": {
                "raw": domain.out_of_scope_atoms.raw,
                "atoms": domain.out_of_scope_atoms.atoms,
            },
        }



def main() -> None:
    parser = argparse.ArgumentParser(description="根据 domain id/name 查询功能域内容")
    parser.add_argument("--yaml", required=True, help="YAML 模板路径")
    parser.add_argument("--domain", required=True, help="功能域编号或名称，例如 Dom-3")
    parser.add_argument("--base-domain", help="模板域依赖的基础功能域，例如 Dom-10")
    parser.add_argument("--target-action-atom", help="模板中的目标动作原子，例如 O2/C3/U2")
    args = parser.parse_args()

    service = DomainQueryService(args.yaml)
    result = service.get_domain_info(
        args.domain,
        base_domain=args.base_domain,
        target_action_atom=args.target_action_atom,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def get_domains_mini_privilege(query_domain,yaml='./domains.yaml',):
    service = DomainQueryService(yaml)
    result = service.get_domain_info(
        query_domain
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    # result = json.dumps(result, ensure_ascii=False, indent=2)
    # print(result['minimum_permission_set']['atoms'])
    return result['minimum_permission_set']['atoms']

if __name__ == "__main__":
    x = get_domains_mini_privilege('Dom-3')
    print(x)
