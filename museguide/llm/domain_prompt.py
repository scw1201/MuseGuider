def build_domain_prior_prompt(domain_cfg: dict) -> str:
    lines = []
    lines.append("【可识别展品列表】")

    for e in domain_cfg.get("exhibits", []):
        alias_str = "、".join(e.get("aliases", []))
        lines.append(f"- {e['name']}（{e['id']}），别名：{alias_str}")

    return "\n".join(lines)