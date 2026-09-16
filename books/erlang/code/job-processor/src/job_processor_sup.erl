-module(job_processor_sup).
-behaviour(supervisor).

-export([start_link/1]).
-export([init/1]).

start_link(Opts) ->
    supervisor:start_link({local, ?MODULE}, ?MODULE, Opts).

init(Opts) ->
    SupFlags = #{strategy => one_for_one,
                 intensity => 5,
                 period => 10},
    WorkerSup = #{id => job_worker_sup,
                  start => {job_worker_sup, start_link, []},
                  restart => permanent,
                  shutdown => infinity,
                  type => supervisor,
                  modules => [job_worker_sup]},
    Processor = #{id => job_processor,
                  start => {job_processor, start_link, [Opts]},
                  restart => permanent,
                  shutdown => 5000,
                  type => worker,
                  modules => [job_processor]},
    {ok, {SupFlags, [WorkerSup, Processor]}}.
