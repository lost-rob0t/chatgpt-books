(defmodule bad-rules
  "Deliberately invalid compile-time fixture for the Event Routing DSL."
  (export (rules 0)))

(defun rules ()
  (event-rules-dsl:routes
   (when-level 'critical 'pager)
   (wat 'nope)))
