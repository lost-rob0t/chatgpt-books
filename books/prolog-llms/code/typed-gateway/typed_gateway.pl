:- module(typed_gateway,
          [ decode_model_response/3,
            gateway_once/3
          ]).

:- use_module(library(http/json), [atom_json_dict/3]).
:- use_module('../relational-task-solver/task_capability',
              [ capability/2,
                execute_capability/2
              ]).

/** <module> Typed model-data boundary -- Project 2, milestone A

This module deliberately separates four different facts that are easy to
collapse in an LLM integration:

  1. bytes/text were valid JSON;
  2. the JSON had the one accepted envelope shape;
  3. the requested operation belongs to the repository-authored capability
     vocabulary and has admissible arguments;
  4. trusted host code chose to execute that validated request.

The model controls only `content` inside a trusted adapter response. Provider,
model and response identifiers come from the adapter envelope and are copied
into provenance; fields inside model JSON cannot replace them.
*/

%!  decode_model_response(+ExpectedRequestId:string,
%!                        +AdapterResponse:dict,
%!                        -Outcome) is det.
%
%   Decode one trusted adapter response. Outcome is either
%   `ok(Proposal)` or `error(Reason)`. The decoder never executes a capability.
decode_model_response(ExpectedRequestId, AdapterResponse, Outcome) :-
    (   valid_expected_request_id(ExpectedRequestId)
    ->  decode_adapter(ExpectedRequestId, AdapterResponse, Outcome)
    ;   Outcome = error(invalid_expected_request_id)
    ).

%!  gateway_once(+ExpectedRequestId:string,
%!               +AdapterResponse:dict,
%!               -Outcome) is det.
%
%   Decode and, only after successful validation, execute one request through
%   Project 1's closed capability dispatcher.
gateway_once(ExpectedRequestId, AdapterResponse, Outcome) :-
    decode_model_response(ExpectedRequestId, AdapterResponse, Decoded),
    execute_decoded(Decoded, Outcome).

execute_decoded(error(Reason), error(Reason)).
execute_decoded(ok(Proposal), Outcome) :-
    Proposal = proposal{request_id:RequestId,
                        capability:Capability,
                        arguments:Arguments,
                        provenance:Provenance},
    (   valid_provenance(Provenance),
        capability(Capability, Arity),
        length(Arguments, Arity),
        maplist(atom, Arguments),
        execute_capability(request(Capability, Arguments), Results)
    ->  Outcome = ok(result{request_id:RequestId,
                            capability:Capability,
                            results:Results,
                            provenance:Provenance})
    ;   Outcome = error(dispatch_rejected)
    ).

valid_expected_request_id(RequestId) :-
    string(RequestId),
    string_length(RequestId, Length),
    Length > 0,
    Length =< 128.

decode_adapter(ExpectedRequestId, AdapterResponse, Outcome) :-
    (   adapter_fields(AdapterResponse, Provider, Model, ResponseId, Content)
    ->  parse_candidate(Content, Parsed),
        validate_parsed(Parsed,
                        ExpectedRequestId,
                        Provider,
                        Model,
                        ResponseId,
                        Outcome)
    ;   Outcome = error(invalid_adapter_envelope)
    ).

adapter_fields(Response, Provider, Model, ResponseId, Content) :-
    is_dict(Response),
    exact_keys(Response, [content, model, provider, response_id]),
    get_dict(provider, Response, Provider),
    get_dict(model, Response, Model),
    get_dict(response_id, Response, ResponseId),
    get_dict(content, Response, Content),
    atom(Provider),
    string(Model),
    string(ResponseId),
    string(Content),
    Model \== "",
    ResponseId \== "".

parse_candidate(Content, Outcome) :-
    atom_string(Atom, Content),
    catch(atom_json_dict(Atom, Dict, [value_string_as(string)]),
          _,
          fail),
    !,
    Outcome = ok(Dict).
parse_candidate(_, error(malformed_json)).

validate_parsed(error(Reason), _, _, _, _, error(Reason)).
validate_parsed(ok(Dict), ExpectedRequestId, Provider, Model, ResponseId, Outcome) :-
    (   is_dict(Dict),
        exact_keys(Dict, [arguments, capability, request_id, schema])
    ->  validate_candidate(Dict,
                           ExpectedRequestId,
                           Provider,
                           Model,
                           ResponseId,
                           Outcome)
    ;   Outcome = error(invalid_candidate_shape)
    ).

validate_candidate(Dict, ExpectedRequestId, Provider, Model, ResponseId, Outcome) :-
    get_dict(schema, Dict, Schema),
    get_dict(request_id, Dict, RequestId),
    get_dict(capability, Dict, CapabilityText),
    get_dict(arguments, Dict, ArgumentsText),
    (   Schema == "task_capability_v1"
    ->  validate_request_id(RequestId,
                            ExpectedRequestId,
                            CapabilityText,
                            ArgumentsText,
                            Provider,
                            Model,
                            ResponseId,
                            Outcome)
    ;   Outcome = error(unsupported_schema)
    ).

validate_request_id(RequestId,
                    ExpectedRequestId,
                    CapabilityText,
                    ArgumentsText,
                    Provider,
                    Model,
                    ResponseId,
                    Outcome) :-
    (   string(RequestId), RequestId == ExpectedRequestId
    ->  validate_capability(CapabilityText,
                            ArgumentsText,
                            RequestId,
                            Provider,
                            Model,
                            ResponseId,
                            Outcome)
    ;   Outcome = error(request_id_mismatch)
    ).

validate_capability(CapabilityText,
                    ArgumentsText,
                    RequestId,
                    Provider,
                    Model,
                    ResponseId,
                    Outcome) :-
    (   string(CapabilityText),
        capability(Capability, Arity),
        atom_string(Capability, CapabilityText)
    ->  validate_arguments(ArgumentsText,
                           Arity,
                           ArgumentsResult),
        build_proposal(ArgumentsResult,
                       RequestId,
                       Capability,
                       Provider,
                       Model,
                       ResponseId,
                       Outcome)
    ;   Outcome = error(unknown_capability)
    ).

validate_arguments(ArgumentsText, Arity, Outcome) :-
    (   is_list(ArgumentsText), length(ArgumentsText, Arity)
    ->  validate_identifier_strings(ArgumentsText, Outcome)
    ;   Outcome = error(invalid_arguments)
    ).

validate_identifier_strings([], ok([])).
validate_identifier_strings([Text|Rest], Outcome) :-
    (   safe_identifier_string(Text)
    ->  atom_string(Atom, Text),
        validate_identifier_strings(Rest, TailOutcome),
        prepend_argument(TailOutcome, Atom, Outcome)
    ;   Outcome = error(invalid_arguments)
    ).

prepend_argument(error(Reason), _, error(Reason)).
prepend_argument(ok(Rest), Atom, ok([Atom|Rest])).

safe_identifier_string(Text) :-
    string(Text),
    string_length(Text, Length),
    Length > 0,
    Length =< 64,
    string_codes(Text, Codes),
    maplist(identifier_code, Codes).

identifier_code(Code) :-
    code_type(Code, alnum),
    !.
identifier_code(0'_).
identifier_code(0'-).

build_proposal(error(Reason), _, _, _, _, _, error(Reason)).
build_proposal(ok(Arguments), RequestId, Capability, Provider, Model, ResponseId,
               ok(proposal{request_id:RequestId,
                           capability:Capability,
                           arguments:Arguments,
                           provenance:provenance{provider:Provider,
                                                 model:Model,
                                                 response_id:ResponseId}})).

valid_provenance(Provenance) :-
    is_dict(Provenance, provenance),
    exact_keys(Provenance, [model, provider, response_id]),
    get_dict(provider, Provenance, Provider),
    get_dict(model, Provenance, Model),
    get_dict(response_id, Provenance, ResponseId),
    atom(Provider),
    string(Model),
    string(ResponseId),
    Model \== "",
    ResponseId \== "".

exact_keys(Dict, Expected) :-
    dict_pairs(Dict, _, Pairs),
    pairs_keys(Pairs, Keys),
    msort(Keys, SortedKeys),
    msort(Expected, SortedExpected),
    SortedKeys == SortedExpected.
