-module(otp_worker_sup).
-behaviour(supervisor).

-export([start_link/0, stop/0, worker_pid/0]).
-export([init/1]).

start_link() ->
    supervisor:start_link({local, ?MODULE}, ?MODULE, []).

stop() ->
    supervisor:stop(?MODULE).

worker_pid() ->
    whereis(otp_worker).

init([]) ->
    SupFlags = #{
        strategy => one_for_one,
        intensity => 2,
        period => 60
    },
    Worker = #{
        id => otp_worker,
        start => {otp_worker, start_link, [otp_worker]},
        restart => permanent,
        shutdown => 5000,
        type => worker,
        modules => [otp_worker]
    },
    {ok, {SupFlags, [Worker]}}.
