-module(otp_worker).
-behaviour(gen_server).

-export([
    start/0,
    start_link/0,
    start_link/1,
    publish/3,
    publish_async/3,
    history/2,
    delayed_echo/4,
    crash/2,
    stop/1
]).

-export([
    init/1,
    handle_call/3,
    handle_cast/2,
    handle_info/2,
    terminate/2
]).

start() ->
    gen_server:start(?MODULE, [], []).

start_link() ->
    gen_server:start_link(?MODULE, [], []).

start_link(Name) when is_atom(Name) ->
    gen_server:start_link({local, Name}, ?MODULE, [], []).

publish(Server, Topic, Payload) ->
    gen_server:call(Server, {publish, Topic, Payload}).

publish_async(Server, Topic, Payload) ->
    gen_server:cast(Server, {publish, Topic, Payload}).

history(Server, Topic) ->
    gen_server:call(Server, {history, Topic}).

delayed_echo(Server, Millis, Value, Timeout)
        when is_integer(Millis), Millis >= 0 ->
    gen_server:call(Server, {delayed_echo, Millis, Value}, Timeout).

crash(Server, Reason) ->
    gen_server:call(Server, {crash, Reason}).

stop(Server) ->
    gen_server:stop(Server).

init([]) ->
    {ok, #{next_id => 1, messages => #{}}}.

handle_call({publish, Topic, Payload}, _From, State)
        when is_binary(Topic), is_binary(Payload) ->
    {Id, NextState} = store(Topic, Payload, State),
    {reply, {ok, Id}, NextState};
handle_call({history, Topic}, _From, State) when is_binary(Topic) ->
    Messages = maps:get(messages, State),
    TopicMessages = lists:reverse(maps:get(Topic, Messages, [])),
    {reply, {ok, TopicMessages}, State};
handle_call({delayed_echo, Millis, Value}, _From, State)
        when is_integer(Millis), Millis >= 0 ->
    timer:sleep(Millis),
    {reply, {ok, Value}, State};
handle_call({crash, Reason}, _From, _State) ->
    exit(Reason);
handle_call(Request, _From, State) ->
    {reply, {error, {unknown_request, Request}}, State}.

handle_cast({publish, Topic, Payload}, State)
        when is_binary(Topic), is_binary(Payload) ->
    {_Id, NextState} = store(Topic, Payload, State),
    {noreply, NextState};
handle_cast(_Request, State) ->
    {noreply, State}.

handle_info(_Info, State) ->
    {noreply, State}.

terminate(_Reason, _State) ->
    ok.

store(Topic, Payload, State) ->
    Id = maps:get(next_id, State),
    Messages = maps:get(messages, State),
    TopicMessages = maps:get(Topic, Messages, []),
    Message = #{id => Id, payload => Payload},
    NextMessages = Messages#{Topic => [Message | TopicMessages]},
    {Id, State#{next_id => Id + 1, messages => NextMessages}}.
