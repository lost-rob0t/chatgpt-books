:- module(fake_provider,
          [ fake_response/4
          ]).

/** <module> Deterministic Project 2 model-adapter fixture

This is test and teaching data only. It performs no network I/O and does not
pretend to be a live model. The adapter metadata is supplied by trusted test
code, while CandidateJson represents the untrusted model-controlled payload.
*/

%!  fake_response(+ResponseId:string,
%!                +Model:string,
%!                +CandidateJson:string,
%!                -Response:dict) is det.
fake_response(ResponseId, Model, CandidateJson,
              provider_response{provider:fake,
                                model:Model,
                                response_id:ResponseId,
                                content:CandidateJson}).
