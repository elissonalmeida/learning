import json

import ai
from tone_guard import GENTLE_TONE_RULE

GOAL_MENU = {
    "grow_audience": {"label": "Crescer a minha audiência", "metric": "novos seguidores por mês"},
    "build_authority": {"label": "Construir confiança e autoridade", "metric": "guardados e partilhas por publicação"},
    "get_conversations": {"label": "Ter mais conversas", "metric": "mensagens e comentários por semana"},
    "followers_to_leads": {"label": "Transformar seguidores em contactos", "metric": "inscrições ou pedidos por mês"},
    "leads_to_clients": {"label": "Transformar contactos em clientes", "metric": "marcações ou vendas por mês"},
    "keep_engaged": {"label": "Manter a comunidade envolvida", "metric": "pessoas que interagem repetidamente"},
}

EVIDENCE_LEVELS = ("data", "pattern", "reasoned")


def validate_scored_goals(items, allowed_goals):
    if not isinstance(items, list) or not items:
        raise ai.InvalidAIResponseError("A pontuação dos objectivos não veio como uma lista.")
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            raise ai.InvalidAIResponseError("Um objectivo pontuado tem formato inválido.")
        if item.get("goal") not in allowed_goals:
            raise ai.InvalidAIResponseError(f"Objectivo desconhecido: {item.get('goal')!r}.")
        if item["goal"] in seen:
            raise ai.InvalidAIResponseError(f"Objectivo repetido: {item['goal']!r}.")
        seen.add(item["goal"])
        score = item.get("score")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 100:
            raise ai.InvalidAIResponseError("A pontuação tem de estar entre 0 e 100.")
        if item.get("evidence") not in EVIDENCE_LEVELS:
            raise ai.InvalidAIResponseError("O nível de evidência é inválido.")
        reasons = item.get("reasons")
        if not isinstance(reasons, list) or not reasons or not all(isinstance(r, str) for r in reasons):
            raise ai.InvalidAIResponseError("Cada objectivo precisa de pelo menos uma razão.")
        if not isinstance(item.get("metric"), str) or not isinstance(item.get("target"), str):
            raise ai.InvalidAIResponseError("Cada objectivo precisa de métrica e meta.")
    return items


def score_goals(client, profile, evidence):
    prompt = ai.render_prompt(ai.load_prompt("score_goals"), tone_rule=GENTLE_TONE_RULE)
    goal_lines = "\n".join(
        f"- {key}: {GOAL_MENU[key]['label']} (métrica base: {GOAL_MENU[key]['metric']})"
        for key in profile["goals"]
    )
    prompt = (
        f"{prompt}\n\n## Perfil\n{json.dumps(profile, ensure_ascii=False)}"
        f"\n\n## Objectivos escolhidos\n{goal_lines}"
        f"\n\n## Evidências\n{json.dumps(evidence, ensure_ascii=False)}"
    )
    text, tokens_in, tokens_out = ai._call_claude(client, prompt)
    items = validate_scored_goals(ai._parse_json_response(text), list(profile["goals"]))
    has_windsor = bool(evidence.get("windsor"))
    has_findings = bool(evidence.get("findings"))
    for item in items:
        if item["evidence"] == "data" and not has_windsor:
            item["evidence"] = "reasoned"
        if item["evidence"] == "pattern" and not has_findings:
            item["evidence"] = "reasoned"
    items.sort(key=lambda i: i["score"], reverse=True)
    for rank, item in enumerate(items, start=1):
        item["rank"] = rank
    return items, tokens_in, tokens_out, ai.calculate_cost(tokens_in, tokens_out)
