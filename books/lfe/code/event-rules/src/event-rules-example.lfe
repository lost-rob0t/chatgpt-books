(defmodule event-rules-example
  "Compiled consumer proving the exported macro surface works across modules."
  (export (compiled-rules 0)
          (route-critical 0)))

(defun compiled-rules ()
  (event-rules-dsl:routes
   (when-level 'critical 'pager)
   (when-service 'billing 'billing-queue)
   (otherwise 'archive)))

(defun route-critical ()
  (event-rules:route
   (tuple 'event 'critical 'edge '#"disk full")
   (compiled-rules)))
