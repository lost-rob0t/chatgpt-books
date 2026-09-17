-module(job_worker).
-behaviour(gen_server).

-export([start_link/4, run/1]).
-export([init/1, handle_call/3, handle_cast/2, handle_info/2,
         terminate/2, code_change/3]).

-define(RESULT_GRACE_MS, 1000).

start_link(Owner, JobId, Attempt, Payload) ->
    gen_server:start_link(?MODULE,
                          #{owner => Owner,
                            job_id => JobId,
                            attempt => Attempt,
                            payload => Payload,
                            status => ready},
                          []).

run(Pid) ->
    gen_server:cast(Pid, run).

init(State) ->
    {ok, State}.

handle_call(Request, _From, State) ->
    {reply, {error, {unsupported_call, Request}}, State}.

handle_cast(run,
            State = #{status := ready,
                      owner := Owner,
                      job_id := JobId,
                      attempt := Attempt,
                      payload := Payload}) ->
    run_payload(Payload, Owner, JobId, Attempt, State);
handle_cast(run, State) ->
    {noreply, State};
handle_cast(_Message, State) ->
    {noreply, State}.

handle_info(stop_after_result, State) ->
    {stop, normal, State};
handle_info(_Message, State) ->
    {noreply, State}.

terminate(_Reason, _State) ->
    ok.

code_change(_OldVsn, State, _Extra) ->
    {ok, State}.

run_payload({echo, Value}, Owner, JobId, Attempt, State) ->
    report_success(Owner, JobId, Attempt, Value, State);
run_payload({gate, GatePid, GateRef, Value}, Owner, JobId, Attempt, State) ->
    GatePid ! {worker_waiting, JobId, Attempt, GateRef, self()},
    receive
        {release, GateRef} ->
            report_success(Owner, JobId, Attempt, Value, State)
    after 30000 ->
        exit({gate_timeout, GateRef})
    end;
run_payload({crash_until, CrashThroughAttempt, Value},
            Owner, JobId, Attempt, State)
  when is_integer(CrashThroughAttempt), CrashThroughAttempt >= 0 ->
    case Attempt =< CrashThroughAttempt of
        true ->
            exit({deliberate_crash, Attempt});
        false ->
            report_success(Owner, JobId, Attempt, Value, State)
    end;
run_payload(Payload, _Owner, _JobId, _Attempt, _State) ->
    exit({unsupported_job, Payload}).

report_success(Owner, JobId, Attempt, Value, State) ->
    Owner ! {job_finished, JobId, Attempt, self(), {ok, Value}},
    _Timer = erlang:send_after(?RESULT_GRACE_MS, self(), stop_after_result),
    {noreply, State#{status => finished}}.
