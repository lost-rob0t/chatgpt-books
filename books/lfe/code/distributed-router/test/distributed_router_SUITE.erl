-module(distributed_router_SUITE).

-export([all/0,
         init_per_suite/1,
         remote_route/1,
         node_loss_is_observable/1]).

all() ->
    [remote_route,
     node_loss_is_observable].

init_per_suite(Config) ->
    case node() of
        nonode@nohost ->
            {skip, origin_node_is_not_distributed};
        _ ->
            case code:ensure_loaded(peer) of
                {module, peer} -> Config;
                {error, Reason} -> {skip, {peer_unavailable, Reason}}
            end
    end.

remote_route(_Config) ->
    {Peer, Node} = start_router_peer(),
    try
        pager = route_critical(Node),
        undefined = whereis('otp-router'),
        SupPid = rpc:call(Node, erlang, whereis, ['otp-router-sup']),
        RouterPid = rpc:call(Node, erlang, whereis, ['otp-router']),
        true = is_pid(SupPid),
        true = is_pid(RouterPid),
        Node = node(SupPid),
        Node = node(RouterPid),
        ok
    after
        stop_peer(Peer)
    end.

node_loss_is_observable(_Config) ->
    {Peer, Node} = start_router_peer(),
    true = erlang:monitor_node(Node, true),
    try
        pager = route_critical(Node),
        ok = peer:stop(Peer),
        receive
            {nodedown, Node} -> ok
        after 5000 ->
            ct:fail({missing_nodedown, Node})
        end,
        Result = catch gen_server:call({'otp-router', Node}, get_rules, 1000),
        case contains_nodedown(Node, Result) of
            true -> ok;
            false -> ct:fail({expected_remote_nodedown_exit, Result})
        end
    after
        erlang:monitor_node(Node, false),
        stop_peer(Peer)
    end.

start_router_peer() ->
    BeamDir = filename:dirname(code:which('otp-router')),
    Name = peer:random_name("lfe_book_dist"),
    Cookie = atom_to_list(erlang:get_cookie()),
    Options = #{name => Name,
                args => ["-setcookie", Cookie, "-pa", BeamDir]},
    case peer:start_link(Options) of
        {ok, Peer, Node} ->
            pong = net_adm:ping(Node),
            ok = remote_application_start(Node),
            {Peer, Node};
        Other ->
            ct:fail({peer_start_failed, Other})
    end.

remote_application_start(Node) ->
    case rpc:call(Node, application, load, [otp_router]) of
        ok -> ok;
        {error, {already_loaded, otp_router}} -> ok;
        OtherLoad -> ct:fail({remote_application_load_failed, OtherLoad})
    end,
    case rpc:call(Node, application, start, [otp_router]) of
        ok -> ok;
        {error, {already_started, otp_router}} -> ok;
        OtherStart -> ct:fail({remote_application_start_failed, OtherStart})
    end.

route_critical(Node) ->
    Event = {event, critical, edge, <<"disk full">>},
    case gen_server:call({'otp-router', Node}, {route, Event}, 2000) of
        {ok, Destination} -> Destination;
        Other -> ct:fail({unexpected_route_reply, Other})
    end.

stop_peer(Peer) ->
    case catch peer:stop(Peer) of
        ok -> ok;
        {'EXIT', _} -> ok;
        _ -> ok
    end.

contains_nodedown(Node, {'EXIT', Reason}) ->
    contains_nodedown(Node, Reason);
contains_nodedown(Node, {nodedown, Node}) ->
    true;
contains_nodedown(Node, Tuple) when is_tuple(Tuple) ->
    lists:any(fun(Element) -> contains_nodedown(Node, Element) end,
              tuple_to_list(Tuple));
contains_nodedown(Node, List) when is_list(List) ->
    lists:any(fun(Element) -> contains_nodedown(Node, Element) end, List);
contains_nodedown(_Node, _Other) ->
    false.
