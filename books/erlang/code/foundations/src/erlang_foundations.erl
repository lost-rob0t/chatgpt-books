-module(erlang_foundations).

-export([classify/1, sum/1, normalize_command/1]).

classify(N) when is_integer(N), N < 0 ->
    negative_integer;
classify(N) when is_integer(N) ->
    non_negative_integer;
classify(<<>>) ->
    empty_binary;
classify(Bin) when is_binary(Bin) ->
    binary;
classify([]) ->
    empty_list;
classify([_ | _]) ->
    list;
classify(_) ->
    other.

sum(Values) ->
    sum(Values, 0).

sum([], Acc) ->
    Acc;
sum([Head | Tail], Acc) when is_integer(Head) ->
    sum(Tail, Acc + Head).

normalize_command({publish, Topic, Payload})
        when is_binary(Topic), is_binary(Payload) ->
    {ok, {publish, Topic, Payload}};
normalize_command({history, Topic}) when is_binary(Topic) ->
    {ok, {history, Topic}};
normalize_command(Command) ->
    {error, {invalid_command, Command}}.
