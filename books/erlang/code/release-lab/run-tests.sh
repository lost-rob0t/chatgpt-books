#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
APP_ROOT="$(cd "$ROOT/../otp-worker" && pwd)"
BUILD="$(mktemp -d)"
trap 'rm -rf "$BUILD"' EXIT

APP_EBIN="$BUILD/lib/otp_worker_app-0.1.0/ebin"
REL_DIR="$BUILD/release"
mkdir -p "$APP_EBIN" "$REL_DIR"

erlc -Werror -o "$APP_EBIN" "$APP_ROOT"/src/*.erl
cp "$APP_ROOT/src/otp_worker_app.app.src" "$APP_EBIN/otp_worker_app.app"

ERTS_VSN="$(erl -noshell -eval 'io:format("~s", [erlang:system_info(version)]), halt().' )"
KERNEL_VSN="$(erl -noshell -eval '{ok,V}=application:get_key(kernel,vsn), io:format("~s",[V]), halt().' )"
STDLIB_VSN="$(erl -noshell -eval '{ok,V}=application:get_key(stdlib,vsn), io:format("~s",[V]), halt().' )"
REL_BASE="$REL_DIR/otp_worker_release"

cat > "$REL_BASE.rel" <<REL
{release,
 {"otp_worker_release", "0.1.0"},
 {erts, "$ERTS_VSN"},
 [{kernel, "$KERNEL_VSN"},
  {stdlib, "$STDLIB_VSN"},
  {otp_worker_app, "0.1.0"}]}.
REL

# Local boot scripts keep the actual application directories. That is useful for
# exercising a generated boot file in CI without pretending the temporary build
# directory is an installed target-system root.
erl -noshell -pa "$APP_EBIN" -eval "
  case systools:make_script(\"$REL_BASE\", [{path,[\"$APP_EBIN\"]}, local, no_warn_sasl, warnings_as_errors, silent]) of
      {ok,_,[]} -> halt(0);
      {ok,Mod,Warnings} -> io:format(\"unexpected warnings ~p: ~p~n\", [Mod,Warnings]), halt(1);
      Other -> io:format(\"make_script failed: ~p~n\", [Other]), halt(1)
  end."

test -s "$REL_BASE.script"
test -s "$REL_BASE.boot"

erl -noshell -boot "$REL_BASE" -eval '
  Apps = application:which_applications(),
  Sup = whereis(otp_worker_sup),
  Worker = whereis(otp_worker),
  case {lists:keyfind(otp_worker_app, 1, Apps), Sup, Worker} of
      {{otp_worker_app, _, "0.1.0"}, SupPid, WorkerPid}
        when is_pid(SupPid), is_pid(WorkerPid) ->
          case application:get_application(WorkerPid) of
              {ok, otp_worker_app} -> halt(0);
              OtherOwner -> io:format("unexpected owner: ~p~n", [OtherOwner]), halt(1)
          end;
      Other -> io:format("release boot did not own expected tree: ~p~n", [Other]), halt(1)
  end.'

# A .rel version must agree with the corresponding .app version. The failure is
# asserted structurally; the test does not depend on human-oriented error text.
BAD_VERSION_BASE="$REL_DIR/bad_version_release"
sed 's/{otp_worker_app, "0.1.0"}/{otp_worker_app, "9.9.9"}/' \
  "$REL_BASE.rel" > "$BAD_VERSION_BASE.rel"
erl -noshell -pa "$APP_EBIN" -eval "
  case systools:make_script(\"$BAD_VERSION_BASE\", [{path,[\"$APP_EBIN\"]}, local, no_warn_sasl, silent]) of
      {error,_,_} -> halt(0);
      Other -> io:format(\"expected version mismatch failure, got: ~p~n\", [Other]), halt(1)
  end."

# The application resource is also part of the release dependency contract.
# Here we inject a dependency on crypto but deliberately omit crypto from .rel.
MISSING_EBIN="$BUILD/missing-dependency/ebin"
mkdir -p "$MISSING_EBIN"
cp "$APP_EBIN"/*.beam "$MISSING_EBIN/"
sed 's/{applications, \[kernel, stdlib\]}/{applications, [kernel, stdlib, crypto]}/' \
  "$APP_EBIN/otp_worker_app.app" > "$MISSING_EBIN/otp_worker_app.app"
MISSING_BASE="$REL_DIR/missing_dependency_release"
cp "$REL_BASE.rel" "$MISSING_BASE.rel"
erl -noshell -pa "$MISSING_EBIN" -eval "
  case systools:make_script(\"$MISSING_BASE\", [{path,[\"$MISSING_EBIN\"]}, local, no_warn_sasl, silent]) of
      {error,_,_} -> halt(0);
      Other -> io:format(\"expected missing dependency failure, got: ~p~n\", [Other]), halt(1)
  end."

# Recreate a relocatable boot script and package. Unlike the local script above,
# the resulting script refers to $ROOT/lib/App-Vsn/ebin-style locations.
erl -noshell -pa "$APP_EBIN" -eval "
  case systools:make_script(\"$REL_BASE\", [{path,[\"$APP_EBIN\"]}, no_warn_sasl, warnings_as_errors, silent]) of
      {ok,_,[]} -> ok;
      {ok,Mod,Warnings} -> io:format(\"unexpected packaging warnings ~p: ~p~n\", [Mod,Warnings]), halt(1);
      Other1 -> io:format(\"relocatable make_script failed: ~p~n\", [Other1]), halt(1)
  end,
  case systools:make_tar(\"$REL_BASE\", [{path,[\"$APP_EBIN\"]}, no_warn_sasl, warnings_as_errors, silent]) of
      {ok,_,[]} -> halt(0);
      {ok,Mod2,Warnings2} -> io:format(\"unexpected tar warnings ~p: ~p~n\", [Mod2,Warnings2]), halt(1);
      Other2 -> io:format(\"make_tar failed: ~p~n\", [Other2]), halt(1)
  end."

PACKAGE="$REL_BASE.tar.gz"
test -s "$PACKAGE"
tar -tzf "$PACKAGE" > "$BUILD/package-contents.txt"
grep -q '^lib/otp_worker_app-0.1.0/ebin/otp_worker_app.app$' "$BUILD/package-contents.txt"
grep -q '^lib/otp_worker_app-0.1.0/ebin/otp_worker.beam$' "$BUILD/package-contents.txt"
grep -q '^releases/0.1.0/start.boot$' "$BUILD/package-contents.txt"
grep -q '^releases/0.1.0/otp_worker_release.rel$' "$BUILD/package-contents.txt"
grep -q '^releases/otp_worker_release.rel$' "$BUILD/package-contents.txt"

printf 'release-lab: PASS (ERTS %s, kernel %s, stdlib %s)\n' \
  "$ERTS_VSN" "$KERNEL_VSN" "$STDLIB_VSN"
