:- module(field_service_domain,
          [ field_service_schemas/1,
            field_service_initial_state/1,
            field_service_goal/1,
            impossible_field_service_goal/1
          ]).

%% field_service_schemas(-Schemas) is det.
%
% Synthetic teaching operators.  The variables are local to each schema; the
% planner freshens every schema again before each applicability attempt.
field_service_schemas(
    [ schema(pick_part,
             pick_up(PickTech, PickPart, PickPlace),
             [ tech_at(PickTech, PickPlace),
               part_at(PickPart, PickPlace)
             ],
             [ carrying(PickTech, PickPart) ],
             [ part_at(PickPart, PickPlace) ]),
      schema(travel,
             travel(TravelTech, From, To),
             [ tech_at(TravelTech, From),
               link(From, To)
             ],
             [ tech_at(TravelTech, To) ],
             [ tech_at(TravelTech, From) ]),
      schema(replace_psu,
             replace_psu(RepairTech, Node, NewPart, OldPart),
             [ tech_at(RepairTech, Site),
               hosts(Site, Node),
               carrying(RepairTech, NewPart),
               installed(Node, OldPart),
               failed(Node),
               credential(RepairTech, Node)
             ],
             [ installed(Node, NewPart),
               restored(Node)
             ],
             [ installed(Node, OldPart),
               failed(Node),
               carrying(RepairTech, NewPart)
             ])
    ]).

field_service_initial_state(
    [ credential(tech1, node7),
      failed(node7),
      hosts(site_a, node7),
      installed(node7, psu_old),
      link(depot, site_a),
      link(site_a, depot),
      part_at(psu42, depot),
      tech_at(tech1, depot),
      ticket_open(inc7)
    ]).

field_service_goal([restored(node7)]).

impossible_field_service_goal([restored(node999)]).
