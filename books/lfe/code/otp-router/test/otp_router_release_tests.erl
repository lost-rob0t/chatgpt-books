-module(otp_router_release_tests).

-export([application_lifecycle/0, boot_state/0]).

application_lifecycle() ->
    ok = application:load(otp_router),
    ok = application:start(otp_router),
    ok = assert_running_tree(),
    ok = application:stop(otp_router),
    ok = wait_for_name_gone('otp-router', 100),
    ok = wait_for_name_gone('otp-router-sup', 100),
    ok.

boot_state() ->
    Apps = application:which_applications(),
    case lists:keyfind(otp_router, 1, Apps) of
        {otp_router, _, "0.1.0"} -> ok;
        Other -> erlang:error({unexpected_boot_application, Other})
    end,
    assert_running_tree().

assert_running_tree() ->
    Worker = whereis('otp-router'),
    Sup = whereis('otp-router-sup'),
    true = is_pid(Worker),
    true = is_pid(Sup),
    true = is_process_alive(Worker),
    true = is_process_alive(Sup),
    {ok, pager} = 'otp-router':route('event-rules':'sample-event'(), 1000),
    {ok, otp_router} = application:get_application(Worker),
    ok.

wait_for_name_gone(Name, 0) ->
    erlang:error({registered_name_did_not_stop, Name, whereis(Name)});
wait_for_name_gone(Name, Attempts) ->
    case whereis(Name) of
        undefined -> ok;
        _Pid ->
            timer:sleep(10),
            wait_for_name_gone(Name, Attempts - 1)
    end.
