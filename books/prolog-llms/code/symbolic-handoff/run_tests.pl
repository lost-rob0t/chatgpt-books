:- initialization(main, main).

main :-
    load_files([test_handoff_workbench], [silent(true)]),
    (   current_test_unit(symbolic_handoff)
    ->  (   run_tests([symbolic_handoff])
        ->  halt(0)
        ;   halt(1)
        )
    ;   print_message(error, missing_test_unit(symbolic_handoff)),
        halt(1)
    ).
