from __future__ import annotations

import argparse

from core import build_domains_from_markdown, dump_domains_to_yaml


def main() -> None:
    parser = argparse.ArgumentParser(description="将 Markdown 功能映射表转换为 YAML 模板")
    parser.add_argument("--markdown", required=True, help="Markdown 文件路径")
    parser.add_argument("--output", required=True, help="输出 YAML 文件路径")
    args = parser.parse_args()

    domains = build_domains_from_markdown(args.markdown)
    dump_domains_to_yaml(domains, args.output)

    print(f"已生成 YAML: {args.output}")
    print(f"共转换 {len(domains)} 个功能域")


if __name__ == "__main__":
    main()
