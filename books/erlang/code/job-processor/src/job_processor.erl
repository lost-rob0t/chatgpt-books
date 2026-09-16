-module(job_processor).
-behaviour(gen_server).

-export([start_link/1, submit/1, stats/0]).
-export([init/1, handle_call/3, handle_cast/2, handle_info/2,
         terminate/2, code_change/3]).

start_link(Opts) ->
    gen_server:start_link({local, ?MODULE}, ?MODULE, Opts, []).

submit(Payload) ->
    gen_server:call(?MODULE, {submit, Payload}).

stats() ->
    gen_server:call(?MODULE, stats).

init(Opts) when is_map(Opts) ->
    MaxActive = maps:get(max_active, Opts, 2),
    MaxQueued = maps:get(max_queued, Opts, 4),
    MaxAttempts = maps:get(max_attempts, Opts, 2),
    true = is_integer(MaxActive) andalso MaxActive > 0,
    true = is_integer(MaxQueued) andalso MaxQueued >= 0,
    true = is_integer(MaxAttempts) andalso MaxAttempts > 0,
    {ok, #{max_active => MaxActive,
           max_queued => MaxQueued,
           max_attempts => MaxAttempts,
           pending => queue:new(),
           pending_len => 0,
           active => #{},
           completed => 0,
           failed => 0,
           retried => 0,
           rejected => 0}}.

handle_call({submit, Payload}, {Client, _Tag}, State) ->
    Capacity = maps:get(max_active, State) + maps:get(max_queued, State),
    case outstanding(State) >= Capacity of
        true ->
            Rejected = maps:get(rejected, State),
            {reply, {error, overloaded}, State#{rejected => Rejected + 1}};
        false ->
            JobId = erlang:unique_integer([monotonic, positive]),
            Job = #{id => JobId,
                    attempt => 1,
                    payload => Payload,
                    client => Client},
            State1 = enqueue(Job, State),
            {reply, {ok, JobId}, dispatch(State1)}
    end;
handle_call(stats, _From, State) ->
    Reply = #{active => map_size(maps:get(active, State)),
              queued => maps:get(pending_len, State),
              completed => maps:get(completed, State),
              failed => maps:get(failed, State),
              retried => maps:get(retried, State),
              rejected => maps:get(rejected, State),
              max_active => maps:get(max_active, State),
              max_queued => maps:get(max_queued, State),
              max_attempts => maps:get(max_attempts, State)},
    {reply, Reply, State};
handle_call(Request, _From, State) ->
    {reply, {error, {unsupported_call, Request}}, State}.

handle_cast(_Message, State) ->
    {noreply, State}.

handle_info({job_finished, JobId, Attempt, Pid, Result}, State) ->
    Active = maps:get(active, State),
    case maps:take(Pid, Active) of
        error ->
            {noreply, State};
        {Entry, Active1} ->
            case {maps:get(id, Entry), maps:get(attempt, Entry)} of
                {JobId, Attempt} ->
                    Monitor = maps:get(monitor, Entry),
                    true = erlang:demonitor(Monitor, [flush]),
                    stop_worker(Pid),
                    Client = maps:get(client, Entry),
                    Client ! {job_result, JobId, Result},
                    Completed = maps:get(completed, State),
                    State1 = State#{active => Active1,
                                    completed => Completed + 1},
                    {noreply, dispatch(State1)};
                _Other ->
                    {stop, {worker_protocol_mismatch, Pid, JobId, Attempt}, State}
            end
    end;
handle_info({'DOWN', Monitor, process, Pid, Reason}, State) ->
    Active = maps:get(active, State),
    case maps:take(Pid, Active) of
        error ->
            {noreply, State};
        {Entry, Active1} ->
            case maps:get(monitor, Entry) of
                Monitor ->
                    State1 = State#{active => Active1},
                    {noreply, retry_or_fail(Entry, normalize_exit(Reason), State1)};
                _OtherMonitor ->
                    {stop, {worker_monitor_mismatch, Pid}, State}
            end
    end;
handle_info(_Message, State) ->
    {noreply, State}.

terminate(_Reason, _State) ->
    ok.

code_change(_OldVsn, State, _Extra) ->
    {ok, State}.

outstanding(State) ->
    map_size(maps:get(active, State)) + maps:get(pending_len, State).

enqueue(Job, State) ->
    Pending0 = maps:get(pending, State),
    PendingLen0 = maps:get(pending_len, State),
    State#{pending => queue:in(Job, Pending0),
           pending_len => PendingLen0 + 1}.

dispatch(State) ->
    MaxActive = maps:get(max_active, State),
    PendingLen = maps:get(pending_len, State),
    Active = maps:get(active, State),
    case map_size(Active) < MaxActive andalso PendingLen > 0 of
        false ->
            State;
        true ->
            Pending0 = maps:get(pending, State),
            {{value, Job}, Pending1} = queue:out(Pending0),
            State1 = State#{pending => Pending1,
                            pending_len => PendingLen - 1},
            dispatch(start_job(Job, State1))
    end.

start_job(Job, State) ->
    JobId = maps:get(id, Job),
    Attempt = maps:get(attempt, Job),
    Payload = maps:get(payload, Job),
    StartResult =
        try job_worker_sup:start_job(JobId, Attempt, Payload, self()) of
            Result -> Result
        catch
            exit:Reason -> {error, {worker_supervisor_exit, Reason}}
        end,
    case StartResult of
        {ok, Pid} ->
            Monitor = erlang:monitor(process, Pid),
            Entry = Job#{pid => Pid, monitor => Monitor},
            Active0 = maps:get(active, State),
            job_worker:run(Pid),
            State#{active => Active0#{Pid => Entry}};
        {ok, Pid, _Info} ->
            Monitor = erlang:monitor(process, Pid),
            Entry = Job#{pid => Pid, monitor => Monitor},
            Active0 = maps:get(active, State),
            job_worker:run(Pid),
            State#{active => Active0#{Pid => Entry}};
        {error, Reason} ->
            Client = maps:get(client, Job),
            Client ! {job_result, JobId, {error, {start_failed, Reason}}},
            Failed = maps:get(failed, State),
            State#{failed => Failed + 1}
    end.

retry_or_fail(Entry, Reason, State) ->
    Attempt = maps:get(attempt, Entry),
    MaxAttempts = maps:get(max_attempts, State),
    case Attempt < MaxAttempts of
        true ->
            Job = maps:without([pid, monitor], Entry),
            Retried = maps:get(retried, State),
            State1 = enqueue(Job#{attempt => Attempt + 1},
                             State#{retried => Retried + 1}),
            dispatch(State1);
        false ->
            JobId = maps:get(id, Entry),
            Client = maps:get(client, Entry),
            Client ! {job_result, JobId, {error, {worker_exit, Reason}}},
            Failed = maps:get(failed, State),
            dispatch(State#{failed => Failed + 1})
    end.

normalize_exit(normal) ->
    normal_without_result;
normalize_exit(Reason) ->
    Reason.

stop_worker(Pid) ->
    try gen_server:stop(Pid, normal, 1000) of
        ok -> ok
    catch
        exit:_Reason -> ok
    end.
