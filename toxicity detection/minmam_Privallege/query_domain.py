from __future__ import annotations

import argparse
import json
import re
from typing import Any, Dict, List

from core import load_domains_from_yaml


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

    def get_domain_info(self, domain_key: str) -> Dict[str, Any]:
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
            "minimum_permission_combinations": {
                "raw": domain.minimum_permission_combinations.raw,
                "all_of": domain.minimum_permission_combinations.all_of,
                "one_of": domain.minimum_permission_combinations.one_of,
            },
            "forbidden_atoms": {
                "raw": domain.forbidden_atoms.raw,
                "atoms": domain.forbidden_atoms.atoms,
            },
            "out_of_scope_atoms": {
                "raw": domain.out_of_scope_atoms.raw,
                "atoms": domain.out_of_scope_atoms.atoms,
            },
        }


# ---- helper functions ----
def get_domain_privilege(query_domain: str, yaml: str = "./domains.yaml") -> Dict[str, Any]:
    service = DomainQueryService(yaml)
    return service.get_domain_info(query_domain)


def get_domains_mini_privilege(query_domain: str, yaml: str = "./domains.yaml") -> List[str]:
    result = get_domain_privilege(query_domain, yaml)
    return result["minimum_permission_set"]["atoms"]


def get_domains_minimum_combination(query_domain: str, yaml: str = "./domains.yaml") -> Dict[str, Any]:
    result = get_domain_privilege(query_domain, yaml)
    return result["minimum_permission_combinations"]


def get_domains_forbidden_atoms(query_domain: str, yaml: str = "./domains.yaml") -> List[str]:
    result = get_domain_privilege(query_domain, yaml)
    return result["forbidden_atoms"]["atoms"]


def get_domains_out_of_scope_atoms(query_domain: str, yaml: str = "./domains.yaml") -> List[str]:
    result = get_domain_privilege(query_domain, yaml)
    return result["out_of_scope_atoms"]["atoms"]


# ---- CLI ----
def main() -> None:
    parser = argparse.ArgumentParser(description="根据 domain id/name 查询功能域内容")
    parser.add_argument("--yaml", required=True, help="YAML 模板路径")
    parser.add_argument("--domain", required=True, help="功能域编号或名称，例如 Dom-3")
    parser.add_argument(
        "--field",
        default="all",
        choices=["all", "minimum_set", "minimum_combination", "forbidden", "out_of_scope"],
        help="输出字段，默认 all",
    )
    args = parser.parse_args()

    result = get_domain_privilege(args.domain, args.yaml)

    if args.field == "all":
        output: Any = result
    elif args.field == "minimum_set":
        output = result["minimum_permission_set"]
    elif args.field == "minimum_combination":
        output = result["minimum_permission_combinations"]
    elif args.field == "forbidden":
        output = result["forbidden_atoms"]
    else:
        output = result["out_of_scope_atoms"]

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    # 本地调试示例：
    x = get_domains_mini_privilege('Dom-17')
    print(x)
    # main()
