-module(distributed_service_tests).

-include_lib("eunit/include/eunit.hrl").

request_reply_crosses_real_node_boundary_test_() ->
    {timeout, 20, fun request_reply_crosses_real_node_boundary/0}.

remote_process_crash_is_not_node_failure_test_() ->
    {timeout, 20, fun remote_process_crash_is_not_node_failure/0}.

disconnect_reports_noconnection_without_killing_peer_test_() ->
    {timeout, 20, fun disconnect_reports_noconnection_without_killing_peer/0}.

missing_remote_registration_reports_noproc_test_() ->
    {timeout, 20, fun missing_remote_registration_reports_noproc/0}.

request_reply_crosses_real_node_boundary() ->
    with_peer(fun(_Peer, Node) ->
        true = net_kernel:connect_node(Node),
        {ok, #{node := Node, value := hello}} =
            distributed_service:request(Node, {echo, hello}, 2000)
    end).

remote_process_crash_is_not_node_failure() ->
    with_peer(fun(Peer, Node) ->
        true = net_kernel:connect_node(Node),
        Monitor = erlang:monitor(process, {erlang_book_dist_service, Node}),
        ok = peer:call(Peer, distributed_service, crash, [deliberate_crash]),
        receive
            {'DOWN', Monitor, process, _Object, deliberate_crash} -> ok
        after 2000 ->
            error(remote_process_down_timeout)
        end,
        true = lists:member(Node, nodes()),
        false = peer:call(Peer, distributed_service, running, [])
    end).

disconnect_reports_noconnection_without_killing_peer() ->
    with_peer(fun(Peer, Node) ->
        Options = #{connection_id => true, nodedown_reason => true},
        ok = net_kernel:monitor_nodes(true, Options),
        try
            true = net_kernel:connect_node(Node),
            Up1 = receive_node_event(nodeup, Node),
            Monitor = erlang:monitor(process, {erlang_book_dist_service, Node}),

            true = erlang:disconnect_node(Node),
            receive
                {'DOWN', Monitor, process, _Object, noconnection} -> ok
            after 2000 ->
                error(remote_monitor_did_not_report_noconnection)
            end,
            _Down = receive_node_event(nodedown, Node),
            false = lists:member(Node, nodes()),

            %% peer:call/4 uses the alternative standard-I/O control channel,
            %% so this check does not silently reconnect Erlang Distribution.
            true = peer:call(Peer, distributed_service, running, []),

            true = net_kernel:connect_node(Node),
            Up2 = receive_node_event(nodeup, Node),
            ?assertNotEqual(maps:get(connection_id, Up1),
                            maps:get(connection_id, Up2)),

            Monitor2 = erlang:monitor(process,
                                      {erlang_book_dist_service, Node}),
            {ok, #{node := Node, value := reconnected}} =
                distributed_service:request(Node, {echo, reconnected}, 2000),
            true = erlang:demonitor(Monitor2, [flush])
        after
            ok = net_kernel:monitor_nodes(false, Options)
        end
    end).

missing_remote_registration_reports_noproc() ->
    with_peer(fun(Peer, Node) ->
        true = net_kernel:connect_node(Node),
        ok = peer:call(Peer, distributed_service, stop, []),
        wait_until(fun() ->
            false =:= peer:call(Peer, distributed_service, running, [])
        end, 50),
        {error, noproc} = distributed_service:request(Node, node_identity, 2000)
    end).

with_peer(Fun) ->
    BeamDir = filename:dirname(code:which(distributed_service)),
    Cookie = atom_to_list(erlang:get_cookie()),
    Name = peer:random_name(erlang_book_dist_peer),
    Options = #{
        name => Name,
        connection => standard_io,
        args => ["-setcookie", Cookie,
                 "-kernel", "connect_all", "false",
                 "-pa", BeamDir]
    },
    {ok, Peer, Node} = peer:start_link(Options),
    try
        {ok, _Pid} = peer:call(Peer, distributed_service, start, []),
        Fun(Peer, Node)
    after
        catch peer:call(Peer, distributed_service, stop, []),
        catch peer:stop(Peer)
    end.

receive_node_event(Type, Node) ->
    receive
        {Type, Node, Info} when is_map(Info) -> Info
    after 2000 ->
        error({node_event_timeout, Type, Node})
    end.

wait_until(Predicate, Remaining) when Remaining > 0 ->
    case Predicate() of
        true -> ok;
        false ->
            timer:sleep(10),
            wait_until(Predicate, Remaining - 1)
    end;
wait_until(_Predicate, 0) ->
    error(wait_timeout).
