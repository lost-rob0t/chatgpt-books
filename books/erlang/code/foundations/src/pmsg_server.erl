-module(pmsg_server).

-export([
    start/0,
    call/3,
    publish/4,
    history/3,
    inject_delay/3,
    inject_crash/2,
    stop/2,
    loop/1
]).

start() ->
    spawn(?MODULE, loop, [#{next_id => 1, messages => #{}}]).

publish(Pid, Topic, Payload, Timeout) ->
    call(Pid, {publish, Topic, Payload}, Timeout).

history(Pid, Topic, Timeout) ->
    call(Pid, {history, Topic}, Timeout).

inject_delay(Pid, Millis, Timeout) ->
    call(Pid, {delay, Millis, delayed}, Timeout).

inject_crash(Pid, Reason) ->
    call(Pid, {crash, Reason}, 1000).

stop(Pid, Timeout) ->
    call(Pid, stop, Timeout).

call(Pid, Request, Timeout)
        when is_pid(Pid),
             is_integer(Timeout),
             Timeout >= 0 ->
    Ref = make_ref(),
    Mon = erlang:monitor(process, Pid),
    Pid ! {request, self(), Ref, Request},
    receive
        {reply, Ref, Reply} ->
            erlang:demonitor(Mon, [flush]),
            Reply;
        {'DOWN', Mon, process, Pid, Reason} ->
            {error, {server_down, Reason}}
    after Timeout ->
        erlang:demonitor(Mon, [flush]),
        {error, timeout}
    end.

loop(State) ->
    receive
        {request, From, Ref, {publish, Topic, Payload}}
                when is_pid(From), is_reference(Ref), is_binary(Topic), is_binary(Payload) ->
            NextId = maps:get(next_id, State),
            Messages = maps:get(messages, State),
            TopicMessages = maps:get(Topic, Messages, []),
            Message = #{id => NextId, payload => Payload},
            NextMessages = Messages#{Topic => [Message | TopicMessages]},
            From ! {reply, Ref, {ok, NextId}},
            loop(State#{next_id => NextId + 1, messages => NextMessages});

        {request, From, Ref, {history, Topic}}
                when is_pid(From), is_reference(Ref), is_binary(Topic) ->
            Messages = maps:get(messages, State),
            TopicMessages = lists:reverse(maps:get(Topic, Messages, [])),
            From ! {reply, Ref, {ok, TopicMessages}},
            loop(State);

        {request, From, Ref, {delay, Millis, Value}}
                when is_pid(From), is_reference(Ref), is_integer(Millis), Millis >= 0 ->
            timer:sleep(Millis),
            From ! {reply, Ref, {ok, Value}},
            loop(State);

        {request, _From, _Ref, {crash, Reason}} ->
            exit(Reason);

        {request, From, Ref, stop}
                when is_pid(From), is_reference(Ref) ->
            From ! {reply, Ref, ok},
            ok;

        {request, From, Ref, Request}
                when is_pid(From), is_reference(Ref) ->
            From ! {reply, Ref, {error, {unknown_request, Request}}},
            loop(State);

        _Unexpected ->
            loop(State)
    end.
