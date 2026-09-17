:- begin_tests(typed_gateway).

:- use_module(typed_gateway).
:- use_module(fake_provider).

response(Json, Response) :-
    fake_response("resp-fixture-001", "deterministic-fixture-v1", Json, Response).

valid_json(RequestId, Capability, ArgumentsJson, Json) :-
    format(string(Json),
           '{"schema":"task_capability_v1","request_id":"~s","capability":"~s","arguments":~s}',
           [RequestId, Capability, ArgumentsJson]).

test(decodes_without_execution) :-
    valid_json("req-001", "tasks_by_owner", "[\"ada\"]", Json),
    response(Json, Response),
    decode_model_response("req-001", Response, Outcome),
    assertion(Outcome ==
              ok(proposal{request_id:"req-001",
                          capability:tasks_by_owner,
                          arguments:[ada],
                          provenance:provenance{provider:fake,
                                                model:"deterministic-fixture-v1",
                                                response_id:"resp-fixture-001"}})).

test(executes_only_after_validation) :-
    valid_json("req-002", "tasks_by_owner", "[\"ada\"]", Json),
    response(Json, Response),
    gateway_once("req-002", Response, Outcome),
    Outcome = ok(Result),
    get_dict(results, Result, Results),
    get_dict(provenance, Result, Provenance),
    assertion(Provenance == provenance{provider:fake,
                                       model:"deterministic-fixture-v1",
                                       response_id:"resp-fixture-001"}),
    assertion(Results ==
              [result(task(collect_sources), owner(ada), status(ready),
                      tags([research,prolog])),
               result(task(check_constraints), owner(ada), status(blocked),
                      tags([prolog,validation]))]).

test(two_argument_capability) :-
    valid_json("req-003", "dependency_path",
               "[\"publish_report\",\"collect_sources\"]", Json),
    response(Json, Response),
    gateway_once("req-003", Response, Outcome),
    Outcome = ok(Result),
    get_dict(results, Result, Results),
    assertion(Results ==
              [path([publish_report,write_explanation,check_constraints,
                     normalize_terms,collect_sources])]).

test(rejects_malformed_json) :-
    response("{\"schema\":", Response),
    decode_model_response("req-004", Response, Outcome),
    assertion(Outcome == error(malformed_json)).

test(rejects_extra_candidate_key) :-
    Json = "{\"schema\":\"task_capability_v1\",\"request_id\":\"req-005\",\"capability\":\"tasks_by_owner\",\"arguments\":[\"ada\"],\"provider\":\"trusted-by-model\"}",
    response(Json, Response),
    decode_model_response("req-005", Response, Outcome),
    assertion(Outcome == error(invalid_candidate_shape)).

test(rejects_wrong_schema) :-
    Json = "{\"schema\":\"task_capability_v2\",\"request_id\":\"req-006\",\"capability\":\"tasks_by_owner\",\"arguments\":[\"ada\"]}",
    response(Json, Response),
    decode_model_response("req-006", Response, Outcome),
    assertion(Outcome == error(unsupported_schema)).

test(rejects_request_id_mismatch) :-
    valid_json("different-request", "tasks_by_owner", "[\"ada\"]", Json),
    response(Json, Response),
    decode_model_response("req-007", Response, Outcome),
    assertion(Outcome == error(request_id_mismatch)).

test(rejects_unknown_capability) :-
    valid_json("req-008", "halt", "[]", Json),
    response(Json, Response),
    gateway_once("req-008", Response, Outcome),
    assertion(Outcome == error(unknown_capability)).

test(rejects_wrong_arity) :-
    valid_json("req-009", "tasks_by_owner", "[\"ada\",\"ben\"]", Json),
    response(Json, Response),
    gateway_once("req-009", Response, Outcome),
    assertion(Outcome == error(invalid_arguments)).

test(rejects_code_looking_argument) :-
    valid_json("req-010", "tasks_by_owner", "[\"assertz(pwned)\"]", Json),
    response(Json, Response),
    gateway_once("req-010", Response, Outcome),
    assertion(Outcome == error(invalid_arguments)).

test(model_cannot_replace_adapter_provenance) :-
    Json = "{\"schema\":\"task_capability_v1\",\"request_id\":\"req-011\",\"capability\":\"tasks_by_owner\",\"arguments\":[\"ada\"],\"response_id\":\"forged\"}",
    response(Json, Response),
    decode_model_response("req-011", Response, Outcome),
    assertion(Outcome == error(invalid_candidate_shape)).

test(rejects_adapter_with_extra_field) :-
    valid_json("req-012", "tasks_by_owner", "[\"ada\"]", Json),
    Response = provider_response{provider:fake,
                                 model:"deterministic-fixture-v1",
                                 response_id:"resp-fixture-001",
                                 content:Json,
                                 authority:yes},
    decode_model_response("req-012", Response, Outcome),
    assertion(Outcome == error(invalid_adapter_envelope)).

:- end_tests(typed_gateway).
