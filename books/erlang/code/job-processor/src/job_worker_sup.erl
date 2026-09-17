-module(job_worker_sup).
-behaviour(supervisor).

-export([start_link/0, start_job/4]).
-export([init/1]).

start_link() ->
    supervisor:start_link({local, ?MODULE}, ?MODULE, []).

start_job(JobId, Attempt, Payload, Owner) ->
    ChildSpec = #{id => {job_worker, JobId, Attempt},
                  start => {job_worker, start_link,
                            [Owner, JobId, Attempt, Payload]},
                  restart => temporary,
                  shutdown => 5000,
                  type => worker,
                  modules => [job_worker]},
    supervisor:start_child(?MODULE, ChildSpec).

init([]) ->
    SupFlags = #{strategy => one_for_one,
                 intensity => 5,
                 period => 10},
    {ok, {SupFlags, []}}.
