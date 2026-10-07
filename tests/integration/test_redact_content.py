from __future__ import annotations


def test_redact_content_hides_text_but_keeps_usage_and_timing(
    hook_module,
    fixture_transcript_path,
    read_fixture_jsonl,
    fake_langfuse,
    monkeypatch,
):
    monkeypatch.setattr(hook_module, "REDACT_CONTENT", True)

    transcript = fixture_transcript_path("async_agent_completed")
    rows = read_fixture_jsonl(transcript)
    subagents = hook_module.get_subagent_transcripts_by_tool_use_id(transcript)
    turns = hook_module.build_turns(rows, hook_module.get_task_id_to_tool_use_id(subagents))
    parent_span = fake_langfuse._otel_tracer.start_span(name="parent", start_time=None)

    hook_module.emit_turn_observations(
        fake_langfuse,
        parent_span,
        turns[0],
        hook_module.parse_timestamp(turns[0].user_msg),
        subagent_transcripts_by_tool_use_id=subagents,
    )

    observations = fake_langfuse.observations
    assert observations, "turn should still emit observations"

    # The free-text subagent description must not leak into the span name.
    names = [observation.name for observation in observations]
    assert "Subagent: Summarize docs" not in names
    assert any(name.startswith("Subagent: ") for name in names)

    generation = next(o for o in observations if o.as_type == "generation")
    assert generation.kwargs["input"] == hook_module.REDACTED
    assert generation.kwargs["output"] == hook_module.REDACTED
    # Model/metadata/timing survive redaction untouched (this fixture carries
    # no token usage block, so usage_details is absent with or without redaction).
    assert generation.kwargs.get("model") == "claude-test"
    assert generation.kwargs["metadata"]["tool_count"] == 1
    assert generation._otel_span.start_time is not None

    tool = next(o for o in observations if o.as_type == "tool")
    assert tool.kwargs["input"] == hook_module.REDACTED
    assert tool.output == hook_module.REDACTED
    assert tool.kwargs["metadata"]["subagent_description"] == hook_module.REDACTED

    subagent = next(o for o in observations if o.as_type == "span" and o.name.startswith("Subagent"))
    assert subagent.kwargs["input"] == hook_module.REDACTED
    assert subagent.output == hook_module.REDACTED
