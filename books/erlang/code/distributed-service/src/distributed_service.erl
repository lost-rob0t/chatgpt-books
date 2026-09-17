-module(distributed_service).

-export([start/0, stop/0, crash/1, running/0, request/3]).

-define(NAME, erlang_book_dist_service).

start() ->
    case whereis(?NAME) of
        undefined ->
            Pid = spawn(fun loop/0),
            true = register(?NAME, Pid),
            {ok, Pid};
        Pid ->
            {error, {already_started, Pid}}
    end.

stop() ->
    case whereis(?NAME) of
        undefined -> ok;
        Pid -> Pid ! stop, ok
    end.

crash(Reason) ->
    case whereis(?NAME) of
        undefined -> {error, not_running};
        Pid -> Pid ! {crash, Reason}, ok
    end.

running() ->
    is_pid(whereis(?NAME)).

request(Node, Payload, Timeout)
        when is_atom(Node), is_integer(Timeout), Timeout >= 0 ->
    Target = {?NAME, Node},
    Monitor = erlang:monitor(process, Target),
    Request = make_ref(),
    Target ! {request, self(), Request, Payload},
    receive
        {dist_service_reply, Request, Reply} ->
            true = erlang:demonitor(Monitor, [flush]),
            {ok, Reply};
        {'DOWN', Monitor, process, _Object, noproc} ->
            {error, noproc};
        {'DOWN', Monitor, process, _Object, noconnection} ->
            {error, noconnection};
        {'DOWN', Monitor, process, _Object, Reason} ->
            {error, {remote_exit, Reason}}
    after Timeout ->
        true = erlang:demonitor(Monitor, [flush]),
        {error, timeout}
    end.

loop() ->
    receive
        {request, From, Request, {echo, Value}}
                when is_pid(From), is_reference(Request) ->
            From ! {dist_service_reply, Request,
                    #{node => node(), value => Value}},
            loop();
        {request, From, Request, node_identity}
                when is_pid(From), is_reference(Request) ->
            From ! {dist_service_reply, Request,
                    #{node => node(), pid => self()}},
            loop();
        {crash, Reason} ->
            exit(Reason);
        stop ->
            ok;
        _Other ->
            loop()
    end.
