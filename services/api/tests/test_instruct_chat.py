import asyncio
import json

import pytest

from app import instruct_chat
from test_instruct_runtime import setup  # noqa: F401

PATH = "/api/instruct/v1/chat"


def call(name, args):
    return {"status": "completed", "output": [
        {"type": "function_call", "name": name, "arguments": json.dumps(args), "call_id": "call-1"}]}


def payload(text="What did Friday tell us?", session=None):
    return {"schemaVersion": "instruct.chat.request.v2", "message": text, "sessionId": session}


@pytest.fixture(autouse=True)
def reset():
    instruct_chat.chat_service.sessions.clear()


@pytest.mark.parametrize("message", [
    "What did Friday tell us?", "Can you help me make sense of the assessment?",
    "Who might need a check-in?", "What did the team discuss?",
])
def test_paraphrases_go_to_model_not_a_command_parser(setup, monkeypatch, message):
    client, headers, _, sources, _, settings, _ = setup
    settings.INSTRUCT_CHAT_MODEL = "gpt-5.6-luna"
    seen = []
    async def model(settings, items):
        seen.append(items)
        return call("answer", {"message": "Which assessment would you like to explore?",
                               "factIds": [], "evidenceRefs": []})
    monkeypatch.setattr(instruct_chat, "model_response", model)
    response = client.post(PATH, json=payload(message), headers=headers)
    assert response.status_code == 200, response.text
    assert seen[0][-1]["content"] == message
    assert not sources.calls
    assert response.json()["schemaVersion"] == "instruct.chat.v2"


@pytest.mark.parametrize("source", ["fabric", "foundry"])
def test_authorized_retrieval_and_grounded_fact_selection(setup, monkeypatch, source):
    client, headers, context, sources, _, settings, _ = setup
    settings.INSTRUCT_CHAT_MODEL = "gpt-5.6-luna"
    async def model(settings, items):
        if items[-1].get("type") != "function_call_output":
            return call("retrieve", {**{k: context[k] for k in ("classId", "assessmentId")}, "source": source})
        output = json.loads(items[-1]["output"])
        fact = output["facts"][0]
        available_refs = {ref["refId"] for ref in output["evidenceRefs"]}
        assert fact["evidenceRefs"] and set(fact["evidenceRefs"]) <= available_refs
        assert all(set(ref) == {"refId", "source", "title"} for ref in output["evidenceRefs"])
        return call("answer", {"message": "Consider a short check-in before drawing conclusions.",
                               "factIds": [fact["factId"]], "evidenceRefs": fact["evidenceRefs"]})
    monkeypatch.setattr(instruct_chat, "model_response", model)
    response = client.post(PATH, json=payload(), headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["observations"] and response.json()["observationCitations"]
    assert not response.json()["citations"]
    assert len(sources.calls) == 1


def test_saved_fact_snapshot_keeps_citation_ids_without_source_bodies():
    assert instruct_chat.model_facts([{
        "factId": "fact-1", "kind": "example", "evidenceRefs": ["ref-1"],
        "authority": "assessment", "assessmentId": "assessment-1",
        "effectiveFrom": "2026-10-15T00:00:00Z", "effectiveTo": None,
    }]) == [{"factId": "fact-1", "kind": "example", "evidenceRefs": ["ref-1"]}]


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("selection", ["none", "prose", "observation"])
def test_citations_exclude_unused_retrieved_sources_but_preserve_used_fact_provenance(
    setup, monkeypatch, streaming, selection,
):
    client, headers, context, _, _, _, _ = setup
    expected = set()

    async def model(settings, items):
        if items[-1].get("type") != "function_call_output":
            return call("retrieve", {
                **{k: context[k] for k in ("classId", "assessmentId")}, "source": "foundry",
            })
        output = json.loads(items[-1]["output"])
        all_refs = [ref["refId"] for ref in output["evidenceRefs"]]
        message, fact_ids = "Consider a short check-in.", []
        if selection == "prose":
            expected.update(all_refs[:2])
            message += f" Follow approved requirements [{all_refs[0]}; {all_refs[1]}]. Reuse [{all_refs[0]}]."
        elif selection == "observation":
            fact = output["facts"][0]
            fact_ids = [fact["factId"]]
            expected.update(fact["evidenceRefs"])
        assert len(all_refs) > len(expected)
        return call("answer", {"message": message, "factIds": fact_ids, "evidenceRefs": all_refs})

    monkeypatch.setattr(instruct_chat, "model_response", model)
    response = client.post(PATH, json=payload(), headers={
        **headers, **({"Accept": "text/event-stream"} if streaming else {}),
    })
    assert response.status_code == 200, response.text
    result = stream_events(response)[-1]["payload"] if streaming else response.json()
    published = {ref["refId"] for ref in result["citations"]}
    provenance = {ref["refId"] for ref in result["observationCitations"]}
    assert published == (expected if selection == "prose" else set())
    assert provenance == (expected if selection == "observation" else set())
    assert len(result["citations"]) == len(published)
    assert bool(result["observations"]) == (selection == "observation")


@pytest.mark.parametrize("kind", ["unauthorized", "tool_url", "fabricated_ref", "model_failure", "budget"])
def test_fail_closed_boundaries(setup, monkeypatch, kind):
    client, headers, context, sources, *_ = setup
    async def model(settings, items):
        if kind == "model_failure":
            raise RuntimeError("private upstream content must not appear")
        if kind == "tool_url":
            return call("fetch_url", {"url": "https://evil.invalid"})
        if kind == "fabricated_ref":
            return call("answer", {"message": "Made up", "factIds": [], "evidenceRefs": ["invented"]})
        return call("retrieve", {"classId": "other" if kind == "unauthorized" else context["classId"],
                                 "assessmentId": context["assessmentId"], "source": "fabric"})
    monkeypatch.setattr(instruct_chat, "model_response", model)
    response = client.post(PATH, json=payload(), headers=headers)
    assert response.status_code in (404, 503)
    assert "private upstream" not in response.text
    if kind != "budget":
        assert not sources.calls


def test_no_client_tools_history_or_evidence_and_no_anonymous_access(setup):
    client, headers, *_ = setup
    assert client.post(PATH, json=payload()).status_code == 401
    for extra in ("history", "tools", "evidence", "system"):
        assert client.post(PATH, json={**payload(), extra: []}, headers=headers).status_code == 422
    assert client.post(PATH, json=payload("x" * 2001), headers=headers).status_code == 422


def test_session_history_and_membership_change(setup, monkeypatch):
    client, headers, _, _, _, settings, member = setup
    seen = []
    async def model(settings, items):
        seen.append(items)
        return call("answer", {"message": "What would you like to explore?", "factIds": [], "evidenceRefs": []})
    monkeypatch.setattr(instruct_chat, "model_response", model)
    first = client.post(PATH, json=payload("First question"), headers=headers).json()
    sid = first["sessionId"]
    assert client.post(PATH, json=payload("Follow up", sid), headers=headers).status_code == 200
    assert [i["role"] for i in seen[-1]] == ["developer", "user", "assistant", "user"]
    settings.INSTRUCT_CLASS_GRANTS_JSON = json.dumps([{**member, "revision": "revoked"}])
    assert client.post(PATH, json=payload("Another", sid), headers=headers).status_code == 404


def test_workiq_explicitly_unavailable_without_delegated_setup(setup, monkeypatch):
    client, headers, context, sources, *_ = setup
    async def model(settings, items):
        if items[-1].get("type") != "function_call_output":
            return call("retrieve", {"classId": context["classId"],
                                     "assessmentId": context["assessmentId"], "source": "work"})
        output = json.loads(items[-1]["output"])
        assert output["state"] == "unavailable"
        assert not output["facts"] and "OBO" in output["reason"]
        return call("answer", {"message": "WorkIQ needs operator setup before I can read team discussions.",
                               "factIds": [], "evidenceRefs": []})
    monkeypatch.setattr(instruct_chat, "model_response", model)
    response = client.post(PATH, json=payload("What did the team discuss?"), headers=headers)
    assert response.status_code == 200
    assert not response.json()["citations"] and not sources.calls


def test_chat_service_error_is_not_overwritten_by_cleanup(setup, monkeypatch):
    from fastapi import HTTPException

    client, headers, *_ = setup
    message = "GPT-5.6-luna is rate limited; no fallback model was used."

    async def model(settings, items):
        raise HTTPException(503, message)

    monkeypatch.setattr(instruct_chat, "model_response", model)
    response = client.post(PATH, json=payload(), headers=headers)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "chat_unavailable"
    assert response.json()["error"]["message"] == message
    assert "Authorization unavailable" not in response.text


def stream_events(response):
    assert response.headers["content-type"].startswith("text/event-stream")
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    assert [e["sequence"] for e in events] == list(range(len(events)))
    assert len({e["requestId"] for e in events}) == 1
    assert all(e["schemaVersion"] == "instruct.chat.event.v1" for e in events)
    return events


@pytest.mark.parametrize("source", ["fabric", "foundry", "work"])
def test_chat_stream_reports_actual_calls_and_verified_final(setup, monkeypatch, source):
    client, headers, context, _, _, settings, _ = setup
    settings.INSTRUCT_CHAT_MODEL = "gpt-5.6-luna"

    async def model(settings, items):
        if items[-1].get("type") != "function_call_output":
            return call("retrieve", {**{k: context[k] for k in ("classId", "assessmentId")}, "source": source})
        return call("answer", {"message": "Consider a check-in.", "factIds": [], "evidenceRefs": []})

    monkeypatch.setattr(instruct_chat, "model_response", model)
    response = client.post(PATH, json=payload(), headers={**headers, "Accept": "text/event-stream"})
    events = stream_events(response)
    assert [e["type"] for e in events] == ["started"] + ["progress"] * 8 + ["final"]
    steps = [e["payload"] for e in events if e["type"] == "progress"]
    assert [(s["stage"], s["state"]) for s in steps] == [
        ("model", "running"), ("model", "succeeded"),
        (source, "running"), (source, "unavailable" if source == "work" else "succeeded"),
        ("model", "running"), ("model", "succeeded"),
        ("validation", "running"), ("validation", "succeeded"),
    ]
    assert all(s["durationMs"] >= 0 for s in steps if s["state"] != "running")
    assert steps[3]["evidenceCount"] == (0 if source == "work" else len(
        setup[3].batches[instruct_chat.Source(source)].evidence))
    if source == "work":
        assert "OBO" in steps[3]["message"]
    assert events[-1]["payload"]["schemaVersion"] == "instruct.chat.v2"
    assert not instruct_chat.chat_service.sessions[events[-1]["payload"]["sessionId"]]["busy"]


def test_chat_stream_sanitizes_failure_and_never_emits_final(setup, monkeypatch):
    client, headers, *_ = setup

    async def model(settings, items):
        raise RuntimeError("private upstream content")

    monkeypatch.setattr(instruct_chat, "model_response", model)
    events = stream_events(client.post(PATH, json=payload(), headers={**headers, "Accept": "text/event-stream"}))
    assert [e["type"] for e in events] == ["started", "progress", "progress", "error"]
    assert events[2]["payload"]["state"] == "failed"
    assert "private upstream" not in json.dumps(events)
    assert events[-1]["payload"]["status"] == 503
    assert not next(iter(instruct_chat.chat_service.sessions.values()))["busy"]


def test_model_diagnostics_allowlists_metadata_without_response_content():
    assert instruct_chat.model_diagnostics({
        "id": "private-response", "status": "private-status",
        "incomplete_details": {"reason": "private-reason"},
        "usage": {"input_tokens": 9000, "output_tokens": 1400,
                  "output_tokens_details": {"reasoning_tokens": 1200},
                  "private": "private-usage"},
        "output": [
            {"type": "function_call", "name": "retrieve", "arguments": "private-arguments"},
            {"type": "function_call", "name": "private-tool"},
            {"type": "message", "content": "private-message"},
        ],
    }) == {
        "status": "other", "incomplete_reason": "other",
        "tool_counts": {"retrieve": 1, "answer": 0, "other": 1},
        "input_tokens": 9000, "output_tokens": 1400, "reasoning_tokens": 1200,
    }
    assert instruct_chat.model_diagnostics(None) == {"status": "invalid"}
    assert instruct_chat.model_diagnostics({
        "usage": {"input_tokens": "private", "output_tokens": -1,
                  "output_tokens_details": {"reasoning_tokens": True}},
    }) == {"status": None, "incomplete_reason": None,
           "tool_counts": {"retrieve": 0, "answer": 0, "other": 0}}


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("failure,reason", [
    ("incomplete", "incomplete_model_response"),
    ("budget", "bounded_tool_budget_exceeded"),
    ("invalid_json", "invalid_model_json"),
    ("mixed", "mixed_answer_and_retrieval"),
    ("private_exception", "unexpected_error"),
])
def test_failures_log_safe_reason_and_correlate_with_request(
    setup, monkeypatch, caplog, streaming, failure, reason,
):
    client, headers, *_ = setup

    async def model(settings, items):
        if failure == "private_exception":
            raise ValueError("private-upstream-payload")
        result = call("answer", {
            "message": "private-model-prose", "factIds": [], "evidenceRefs": [],
        })
        if failure == "incomplete":
            result.update(status="incomplete", incomplete_details={"reason": "max_output_tokens"},
                          usage={"input_tokens": 9000, "output_tokens": 1400,
                                 "output_tokens_details": {"reasoning_tokens": 1350}})
        elif failure == "budget":
            result["output"] = []
        elif failure == "invalid_json":
            result["output"][0]["arguments"] = "private-invalid-json"
        elif failure == "mixed":
            result["output"].append({
                "type": "function_call", "name": "private-tool",
                "call_id": "call-2", "arguments": "private-arguments",
            })
        return result

    monkeypatch.setattr(instruct_chat, "model_response", model)
    response = client.post(
        PATH, json=payload("private-user-message"),
        headers={**headers, **({"Accept": "text/event-stream"} if streaming else {})},
    )
    if streaming:
        events = stream_events(response)
        assert events[-1]["type"] == "error"
        assert events[-1]["payload"]["status"] == 503
        rid = events[0]["requestId"]
        message = events[-1]["payload"]["message"]
    else:
        assert response.status_code == 503
        rid = response.json()["requestId"]
        message = response.json()["error"]["message"]
    assert f"Diagnostic ID: {rid}." in message
    assert f"request_id={rid}" in caplog.text
    assert f"reason={reason}" in caplog.text
    assert "model_turn=1" in caplog.text
    if failure == "incomplete":
        assert "response-length limit" in message
        assert '"incomplete_reason": "max_output_tokens"' in caplog.text
        assert '"output_tokens": 1400' in caplog.text
        assert '"reasoning_tokens": 1350' in caplog.text
    assert "private-" not in caplog.text
    assert "private-" not in response.text
    assert not next(iter(instruct_chat.chat_service.sessions.values()))["history"]


def test_chat_stream_denies_anonymous_access_before_stream(setup):
    client, *_ = setup
    response = client.post(PATH, json=payload(), headers={"Accept": "text/event-stream"})
    assert response.status_code == 401
    assert "text/event-stream" not in response.headers["content-type"]


@pytest.mark.asyncio
async def test_stream_exposes_progress_before_model_finishes_and_cancels_on_disconnect(setup, monkeypatch):
    from starlette.requests import Request
    from app.auth import AuthenticatedUser
    from app.instruct_routes import chat

    *_, member = setup
    who = member["principal"]
    user = AuthenticatedUser("", who["tenantId"], who["subject"], frozenset(), {"oid": who["subject"]})
    entered, cancelled = asyncio.Event(), asyncio.Event()

    async def model(settings, items):
        entered.set()
        try:
            await asyncio.Future()
        finally:
            cancelled.set()

    monkeypatch.setattr(instruct_chat, "model_response", model)

    async def receive():
        return {"type": "http.request", "body": json.dumps(payload()).encode()}

    request = Request({"type": "http", "headers": [(b"accept", b"text/event-stream")]}, receive)
    response = await chat(request, user)
    iterator = response.body_iterator
    assert (await anext(iterator))["event"] == "started"
    event = json.loads((await asyncio.wait_for(anext(iterator), 1))["data"])
    assert event["payload"]["stage"] == "model"
    assert event["payload"]["state"] == "running"
    assert entered.is_set()
    saved = next(iter(instruct_chat.chat_service.sessions.values()))
    assert saved["busy"] and not saved["history"]
    await iterator.aclose()
    assert cancelled.is_set()
    assert not saved["busy"] and not saved["history"]


@pytest.mark.asyncio
async def test_transport_requires_exact_model_and_verified_endpoint(setup):
    *_, settings, _ = setup
    for model, endpoint in [
        ("gpt-4.1-mini", "https://own.openai.azure.com"),
        ("gpt-5.6-luna", "https://third-party.invalid"),
    ]:
        settings.INSTRUCT_CHAT_MODEL = model
        settings.INSTRUCT_CHAT_ENDPOINT = endpoint
        settings.INSTRUCT_CHAT_DEPLOYMENT = "instruct-chat-luna"
        with pytest.raises(Exception) as error:
            await instruct_chat.model_response(settings, [])
        assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_transport_reserves_budget_for_reasoning_and_grounded_answer(setup, monkeypatch):
    from types import SimpleNamespace

    import azure.identity.aio
    import httpx

    *_, settings, _ = setup
    settings.INSTRUCT_CHAT_MODEL = "gpt-5.6-luna"
    settings.INSTRUCT_CHAT_ENDPOINT = "https://test.openai.azure.com"
    settings.INSTRUCT_CHAT_DEPLOYMENT = "instruct-chat-luna"

    class Credential:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get_token(self, scope):
            return SimpleNamespace(token="test-token")

    def respond(request):
        body = json.loads(request.content)
        assert str(request.url) == "https://test.openai.azure.com/openai/v1/responses"
        assert body["model"] == "instruct-chat-luna"
        assert body["max_output_tokens"] == 4096
        assert body["reasoning"] == {"effort": "low"}
        assert body["tool_choice"] == "required"
        assert body["store"] is False
        assert body["tools"] == instruct_chat.TOOLS
        return httpx.Response(200, json={"status": "completed", "output": []})

    client = httpx.AsyncClient
    monkeypatch.setattr(azure.identity.aio, "ManagedIdentityCredential", lambda **kwargs: Credential())
    monkeypatch.setattr(
        instruct_chat.httpx, "AsyncClient",
        lambda **kwargs: client(transport=httpx.MockTransport(respond), **kwargs),
    )
    assert await instruct_chat.model_response(settings, []) == {"status": "completed", "output": []}


def parallel_calls(context):
    output = []
    for source in ("fabric", "foundry", "work"):
        item = call("retrieve", {**{k: context[k] for k in ("classId", "assessmentId")}, "source": source})["output"][0]
        output.append({**item, "call_id": f"retrieve-{source}"})
    return {"status": "completed", "output": output}


@pytest.mark.parametrize("streaming", [False, True])
def test_parallel_sources_overlap_have_independent_timing_and_merge_before_answer(setup, monkeypatch, streaming):
    from types import SimpleNamespace

    client, headers, context, sources, _, settings, _ = setup
    settings.INSTRUCT_CHAT_MODEL = "gpt-5.6-luna"
    settings.INSTRUCT_PROVIDER_TIMEOUT_SECONDS = 1
    started, all_started = set(), asyncio.Event()
    foundry_done, work_done = asyncio.Event(), asyncio.Event()
    clock = [100.0]
    monkeypatch.setattr(instruct_chat, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    original = sources.retrieve
    seen = []

    async def enter(source):
        started.add(source)
        if len(started) == 3:
            all_started.set()
        await asyncio.wait_for(all_started.wait(), 0.5)

    async def retrieve(context):
        await enter(context.source.value)
        if context.source.value == "fabric":
            await work_done.wait()
            clock[0] = 103.0
        else:
            clock[0] = 101.0
            foundry_done.set()
        return await original(context)

    async def work(**kwargs):
        assert kwargs["class_id"] == context["classId"]
        await enter("work")
        await foundry_done.wait()
        clock[0] = 102.0
        work_done.set()
        return {
            "state": "succeeded",
            "facts": [{"factId": "work-test", "kind": "work_iq_summary", "evidenceRefs": ["work-ref"]}],
            "evidenceRefs": [{"refId": "work-ref", "source": "work", "title": "Synthetic team suggestion",
                              "locator": "synthetic-test", "excerpt": "Synthetic collaboration."}],
        }

    async def model(settings, items):
        seen.append(list(items))
        outputs = [item for item in items if item.get("type") == "function_call_output"]
        if not outputs:
            return parallel_calls(context)
        assert [item["call_id"] for item in outputs] == ["retrieve-fabric", "retrieve-foundry", "retrieve-work"]
        assert started == {"fabric", "foundry", "work"}
        batches = [json.loads(item["output"]) for item in outputs]
        facts = [batch["facts"][0] for batch in batches]
        return call("answer", {"message": "Consider a short check-in.",
                               "factIds": [f["factId"] for f in facts],
                               "evidenceRefs": [r for f in facts for r in f["evidenceRefs"]]})

    monkeypatch.setattr(sources, "retrieve", retrieve)
    monkeypatch.setattr(instruct_chat, "retrieve_work_context", work)
    monkeypatch.setattr(instruct_chat, "model_response", model)
    response = client.post(PATH, json=payload(), headers={
        **headers, **({"Accept": "text/event-stream"} if streaming else {}),
    })
    assert response.status_code == 200, response.text
    if streaming:
        events = stream_events(response)
        result = events[-1]["payload"]
        steps = [e["payload"] for e in events if e["type"] == "progress"
                 and e["payload"]["stage"] in {"fabric", "foundry", "work"}]
        assert [s["state"] for s in steps[:3]] == ["running"] * 3
        assert [(s["stage"], s["durationMs"]) for s in steps[3:]] == [
            ("foundry", 1000), ("work", 2000), ("fabric", 3000),
        ]
    else:
        result = response.json()
    assert len(seen) == 2
    assert len(result["observations"]) == 3
    assert {r["source"] for r in result["observationCitations"]} == {"fabric", "foundry", "work"}


@pytest.mark.parametrize("invalid", [
    "duplicate_source", "duplicate_id", "cross_scope", "unauthorized", "extra_call",
    "answer_first", "answer_last", "unknown_tool", "invalid_arguments",
])
def test_parallel_batch_is_fully_validated_before_any_retrieval(setup, monkeypatch, invalid):
    client, headers, context, sources, *_ = setup
    result = parallel_calls(context)
    calls = result["output"]
    args = json.loads(calls[1]["arguments"])
    if invalid == "duplicate_source":
        args["source"] = "fabric"
    elif invalid == "duplicate_id":
        calls[1]["call_id"] = calls[0]["call_id"]
    elif invalid == "cross_scope":
        args["classId"] = "other-class"
    elif invalid == "unauthorized":
        for item in calls:
            value = json.loads(item["arguments"])
            value["classId"] = "other-class"
            item["arguments"] = json.dumps(value)
    elif invalid == "extra_call":
        calls.append({**calls[0], "call_id": "extra"})
    elif invalid in {"answer_first", "answer_last"}:
        calls[0 if invalid == "answer_first" else -1] = call(
            "answer", {"message": "Premature answer.", "factIds": [], "evidenceRefs": []},
        )["output"][0]
    elif invalid == "unknown_tool":
        calls[-1]["name"] = "fetch_url"
    if invalid != "unauthorized":
        calls[1]["arguments"] = "[]" if invalid == "invalid_arguments" else json.dumps(args)

    async def model(settings, items):
        return result

    async def work(**kwargs):
        pytest.fail("No source may run before the entire tool batch is authorized and validated")

    monkeypatch.setattr(instruct_chat, "model_response", model)
    monkeypatch.setattr(instruct_chat, "retrieve_work_context", work)
    response = client.post(PATH, json=payload(), headers=headers)
    assert response.status_code in {404, 503}
    assert not sources.calls
    saved = next(iter(instruct_chat.chat_service.sessions.values()))
    assert not saved["history"] and not saved["facts"] and not saved["busy"]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["cancel", "provider_error", "provider_timeout"])
async def test_parallel_failure_joins_all_siblings_and_never_commits_a_partial_turn(setup, monkeypatch, failure):
    from app.auth import AuthenticatedUser
    from fastapi import HTTPException

    _, _, context, sources, runtime, settings, member = setup
    who = member["principal"]
    user = AuthenticatedUser("", who["tenantId"], who["subject"], frozenset(), {"oid": who["subject"]})
    settings.INSTRUCT_PROVIDER_TIMEOUT_SECONDS = 0.05 if failure == "provider_timeout" else 1
    started, stopped, all_started = set(), set(), asyncio.Event()
    updates = []

    async def wait(source):
        started.add(source)
        if len(started) == 3:
            all_started.set()
        try:
            await all_started.wait()
            if failure == "provider_error" and source == "fabric":
                raise ValueError("private source failure")
            await asyncio.Future()
        finally:
            stopped.add(source)

    async def retrieve(context):
        await wait(context.source.value)

    async def work(**kwargs):
        await wait("work")

    async def model(settings, items):
        return parallel_calls(context)

    monkeypatch.setattr(sources, "retrieve", retrieve)
    monkeypatch.setattr(instruct_chat, "retrieve_work_context", work)
    monkeypatch.setattr(instruct_chat, "model_response", model)
    task = asyncio.create_task(instruct_chat.chat_service.run(
        instruct_chat.ChatRequest.model_validate(payload()), user, settings, runtime,
        on_progress=updates.append,
    ))
    await asyncio.wait_for(all_started.wait(), 0.5)
    if failure == "cancel":
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        with pytest.raises(HTTPException) as error:
            await asyncio.wait_for(task, 1)
        assert error.value.status_code == 503
        assert "private source" not in error.value.detail
    assert stopped == started == {"fabric", "foundry", "work"}
    assert {p.stage for p in updates if p.state == "failed"} == started
    saved = next(iter(instruct_chat.chat_service.sessions.values()))
    assert not saved["history"] and not saved["facts"] and not saved["refs"] and not saved["busy"]


def test_parallel_unavailable_source_does_not_discard_other_verified_results(setup, monkeypatch):
    client, headers, context, sources, *_ = setup

    async def model(settings, items):
        outputs = [item for item in items if item.get("type") == "function_call_output"]
        if not outputs:
            return parallel_calls(context)
        data = {item["call_id"]: json.loads(item["output"]) for item in outputs}
        assert data["retrieve-work"]["state"] == "unavailable"
        assert "OBO" in data["retrieve-work"]["reason"]
        fact = data["retrieve-fabric"]["facts"][0]
        assert data["retrieve-foundry"]["state"] == "succeeded"
        return call("answer", {"message": "Team context is unavailable; consider a check-in.",
                               "factIds": [fact["factId"]], "evidenceRefs": fact["evidenceRefs"]})

    monkeypatch.setattr(instruct_chat, "model_response", model)
    events = stream_events(client.post(PATH, json=payload(), headers={**headers, "Accept": "text/event-stream"}))
    assert events[-1]["type"] == "final"
    assert events[-1]["payload"]["observations"]
    assert not any(c["source"] == "work" for c in events[-1]["payload"]["citations"])
    assert len(sources.calls) == 2


def test_parallel_calls_share_the_existing_total_tool_budget(setup, monkeypatch):
    client, headers, context, sources, *_ = setup
    count = 0

    async def model(settings, items):
        nonlocal count
        count += 1
        if count <= 2:
            return parallel_calls(context)
        return call("answer", {"message": "Not within the tool budget.", "factIds": [], "evidenceRefs": []})

    monkeypatch.setattr(instruct_chat, "model_response", model)
    response = client.post(PATH, json=payload(), headers=headers)
    assert response.status_code == 503
    assert count == 3
    assert len(sources.calls) == 4
    assert not next(iter(instruct_chat.chat_service.sessions.values()))["history"]


def test_parallel_results_are_not_published_after_access_changes(setup, monkeypatch):
    client, headers, context, _, _, settings, member = setup

    async def model(settings, items):
        if items[-1].get("type") != "function_call_output":
            return parallel_calls(context)
        settings.INSTRUCT_CLASS_GRANTS_JSON = json.dumps([{**member, "revision": "changed-during-retrieval"}])
        return call("answer", {"message": "Do not publish this.", "factIds": [], "evidenceRefs": []})

    monkeypatch.setattr(instruct_chat, "model_response", model)
    response = client.post(PATH, json=payload(), headers=headers)
    assert response.status_code == 404
    saved = next(iter(instruct_chat.chat_service.sessions.values()))
    assert not saved["history"] and not saved["facts"] and not saved["refs"]


def test_dependent_retrievals_can_still_run_in_later_model_turns(setup, monkeypatch):
    client, headers, context, sources, *_ = setup
    selections = []

    async def model(settings, items):
        outputs = [item for item in items if item.get("type") == "function_call_output"]
        if len(outputs) < 2:
            source = "fabric" if not outputs else "foundry"
            if outputs:
                assert json.loads(outputs[0]["output"])["facts"]
            selections.append(source)
            return call("retrieve", {
                **{k: context[k] for k in ("classId", "assessmentId")}, "source": source,
            })
        return call("answer", {"message": "Consider a short check-in.", "factIds": [], "evidenceRefs": []})

    monkeypatch.setattr(instruct_chat, "model_response", model)
    assert client.post(PATH, json=payload(), headers=headers).status_code == 200
    assert selections == ["fabric", "foundry"]
    assert [c.source.value for c in sources.calls] == selections


@pytest.mark.asyncio
async def test_model_transport_enables_parallel_tool_selection(setup, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    import azure.identity.aio
    import httpx

    *_, settings, _ = setup
    settings.INSTRUCT_CHAT_MODEL = "gpt-5.6-luna"
    settings.INSTRUCT_CHAT_ENDPOINT = "https://synthetic-test.openai.azure.com"
    settings.INSTRUCT_CHAT_DEPLOYMENT = "synthetic-test"
    credential, client = AsyncMock(), AsyncMock()
    credential.__aenter__.return_value = credential
    credential.get_token.return_value = SimpleNamespace(token="synthetic-test-token")
    client.__aenter__.return_value = client
    client.post.return_value = httpx.Response(
        200, json=call("answer", {"message": "Which class?", "factIds": [], "evidenceRefs": []}),
        request=httpx.Request("POST", settings.INSTRUCT_CHAT_ENDPOINT),
    )
    monkeypatch.setattr(azure.identity.aio, "ManagedIdentityCredential", lambda **kwargs: credential)
    monkeypatch.setattr(instruct_chat.httpx, "AsyncClient", lambda **kwargs: client)
    await instruct_chat.model_response(settings, [])
    assert client.post.call_args.kwargs["json"]["parallel_tool_calls"] is True
    assert client.post.call_args.kwargs["json"]["store"] is False
