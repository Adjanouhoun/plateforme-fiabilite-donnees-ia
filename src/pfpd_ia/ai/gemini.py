from __future__ import annotations

from collections.abc import Callable
from typing import Any

from google import genai
from google.genai import types

from pfpd_ia.ai.contracts import GeneratedIncidentExplanation, IncidentFactPackage
from pfpd_ia.ai.providers import ProviderError
from pfpd_ia.config import Settings

SYSTEM_INSTRUCTION = """Tu expliques un incident de qualité de données en français.
Utilise exclusivement les faits JSON fournis. N'invente aucune cause, mesure,
conséquence métier ni action déjà réalisée. Place toute information absente dans
unknowns. diagnostic_leads doit contenir entre une et trois vérifications
proposées, prudentes et directement reliées aux faits disponibles ; ces pistes
ne sont jamais des faits. N'accorde aucun pouvoir décisionnel à cette
explication."""


def _gemini_response_schema() -> dict[str, Any]:
    schema = GeneratedIncidentExplanation.model_json_schema()
    schema["properties"]["diagnostic_leads"]["minItems"] = 1
    schema["properties"]["diagnostic_leads"]["maxItems"] = 3
    return schema


class GeminiIncidentExplanationProvider:
    provider_name = "google_gemini"

    def __init__(
        self,
        *,
        api_key: str,
        model_name: str,
        client_factory: Callable[..., Any] = genai.Client,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Une clé Gemini non vide est requise")
        if not model_name.strip():
            raise ValueError("Un modèle Gemini non vide est requis")
        self._api_key = api_key
        self.model_name = model_name
        self._client_factory = client_factory

    def generate(self, package: IncidentFactPackage) -> GeneratedIncidentExplanation:
        client = self._client_factory(api_key=self._api_key)
        try:
            response = client.models.generate_content(
                model=self.model_name,
                contents=package.model_dump_json(),
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    response_mime_type="application/json",
                    response_json_schema=_gemini_response_schema(),
                    max_output_tokens=2048,
                ),
            )
            if isinstance(response.parsed, GeneratedIncidentExplanation):
                explanation = response.parsed
            elif response.parsed is not None:
                explanation = GeneratedIncidentExplanation.model_validate(response.parsed)
            elif response.text:
                explanation = GeneratedIncidentExplanation.model_validate_json(response.text)
            else:
                raise ProviderError("gemini_empty_response")
            if not 1 <= len(explanation.diagnostic_leads) <= 3:
                raise ProviderError("gemini_diagnostic_leads_invalid")
            return explanation
        except ProviderError:
            raise
        except Exception as error:
            raise ProviderError("gemini_request_failed") from error
        finally:
            client.close()


def gemini_provider_from_settings(
    settings: Settings,
) -> GeminiIncidentExplanationProvider | None:
    if not settings.gemini_enabled or settings.gemini_api_key is None:
        return None
    api_key = settings.gemini_api_key.get_secret_value().strip()
    if not api_key:
        return None
    return GeminiIncidentExplanationProvider(
        api_key=api_key,
        model_name=settings.gemini_model,
    )
