#!/usr/bin/env bats

export HGRCPATH=  # https://stackoverflow.com/q/52584763/113632
export HG_B_SIMPLE_HASHING=true
export HG_B_LOG_TRACEBACKS=true

_hg() {
  # Need to set ui.interactive to disable auto-username selection
  # https://www.mercurial-scm.org/repo/hg/file/4.7/mercurial/ui.py#l837
  command hg \
    --config extensions.b="${BATS_TEST_DIRNAME}/b.py" \
    --config ui.interactive=true \
    "$@"
}

hg() {
  echo "$ hg $*"
  _hg "$@"
  local ret=$?
  printf '%s\n' '-----'
  return $ret
}

run_hg() {
  echo "$ run hg $*"
  run _hg "$@"
  echo "$output"
  printf '%s\n' '-----'
}

setup() {
  local dir
  dir=$(mktemp -d "$BATS_TMPDIR/b-test-$BATS_TEST_NUMBER-XXXXXX")
  cd "$dir"
  _hg init
}

@test "basic flow" {
  # basic sanity check that none of these commands fail
  # separate tests check behavior of individual commands
  hg b
  hg b list
  hg b add some bug
  hg b id 7
  hg b rename 7 another bug
  hg b assign -f 7 user
  hg b resolve 7
  hg b list
  hg b list -r
  hg b reopen 7
  hg b list
  hg b list -r
  hg b comment 7 some comment
  hg b details 7
  EDITOR=cat hg b edit 7
  hg b users
  hg b version
}

@test "add-list-details" {
  hg b add some bug
  run_hg b list
  [[ "$output" =~ "some bug" ]]
  run_hg b details 7
  [[ "$output" =~ "Title: some bug" ]]
}

@test "add supports duplicate names" {
  unset HG_B_SIMPLE_HASHING
  hg b add some bug
  hg b add some bug
  run_hg b list
  (( ${#lines[@]} == 3 )) # two bugs + summary
}

@test "rename" {
  hg b add some bug
  run_hg b list
  [[ "$output" =~ "some bug" ]]
  hg b rename 7 another bug
  run_hg b list
  [[ "$output" =~ "another bug" ]]
  ! [[ "$output" =~ "some bug" ]]
}

@test "edit" {
  hg b add some bug
  EDITOR=cat run_hg b edit 7
  [[ "${lines[0]}" =~ "Lines starting with '#'" ]]

  EDITOR=echo run_hg b edit 7
  echo "Foo Bar" > "$output"

  run_hg b details 7
  [[ "$output" =~ "Foo Bar" ]]
}

@test "comment" {
  hg b add some bug
  hg b comment 7 Foo Bar
  run_hg b details 7
  # Bash 4.3 supports '-1' to mean last index, but we'll stick with this for now
  [[ "${lines[${#lines[@]}-1]}" =~ "Foo Bar" ]]
}

@test "assign" {
  hg b add some bug
  run_hg b users
  [[ "${lines[1]}" =~ ^Nobody: ]]
  hg b assign -f 7 UserName
  run_hg b users
  [[ "${lines[1]}" =~ ^UserName: ]]

  hg b add another bug
  run_hg b assign 8 u
  [[ "$output" =~ .*UserName.* ]]
}

@test "users" {
  hg b add some bug
  hg b add another bug
  hg b assign 7 -f UserA
  hg b assign 8 -f UserB
  run_hg b users
  [[ "$output" =~ .*UserA.* ]]
  [[ "$output" =~ .*UserB.* ]]
}

@test "user-from-config" {
  hg --config ui.username=from-hg --config bugs.user=from-b b add some bug
  run_hg b users
  [[ "${lines[1]}" =~ ^from-b: ]]
  hg --config ui.username=from-hg --config bugs.user=hg.user b assign 7 me
  run_hg b users
  [[ "${lines[1]}" =~ ^from-hg: ]]
  hg --config ui.username=from-hg b assign 7 me
  run_hg b users
  [[ "${lines[1]}" =~ ^from-hg: ]]
  hg b assign 7 me
  run_hg b users
  [[ "${lines[1]}" =~ ^Nobody: ]]
}

@test "resolve-reopen" {
  assert_list_open_closed() {
    run_hg b list
    (( "${#lines[@]}" - 1 == "$1" )) || return
    run_hg b list -r
    (( "${#lines[@]}" - 1 == "$2" )) || return
  }

  hg b add some bug
  assert_list_open_closed 1 0

  hg b resolve 7
  assert_list_open_closed 0 1

  hg b add another bug
  assert_list_open_closed 1 1

  hg b reopen 7
  assert_list_open_closed 2 0
}

@test "list" {
  hg b add some bug
  hg b add another bug
  hg b add resolved bug
  hg b assign 7 -f UserA
  hg b resolve 3

  run_hg b list
  [[ "$output" =~ Found\ 2\ open ]]
  run_hg b list -r
  [[ "$output" =~ Found\ 1\ resolved ]]
  run_hg b list -o UserA
  [[ "$output" =~ Found\ 1\ open ]]
  run_hg b list -g another
  [[ "$output" =~ Found\ 1\ open ]]
  hg b list -a
  hg b list -c

  run_hg b list -r -g solve
  [[ "$output" =~ Found\ 1\ resolved ]]
  run_hg b list -r -o u -a
  [[ "$output" =~ Found\ 0\ resolved ]]
}

@test "id" {
  hg b add some bug
  run_hg b id 7f0
  [[ "$output" == 7f07e8490f2307c8139756893baecad033fa6e7c ]]
}

@test "help" {
  hg b help
}

@test "version" {
  hg b version
}

@test "hg auto-add" {
  hg b add some bug
  EDITOR=cat hg b edit 7

  run_hg stat -u
  (( "${#lines[@]}" == 0 ))
}

@test "--rev" {
  skip "--rev is broken :( "
  hg b add some bug
  hg b assign -f 7 UserA
  EDITOR=cat hg b edit 7

  hg --config ui.username=username commit -m "rev1" -v
  # commit=$(_hg id -i)
  hg b assign -f 7 UserB
  hg b resolve 7
  hg b add another bug

  hg b list


  hg b list --rev 0
  hg b details 7 --rev 0
  hg b users --rev 0
  hg b id 7 --rev 0

  echo DONE; false
}

# Failure Tests
# Ok to remove error-message checks if they become too brittle

@test "bad-db is-dir" {
  mkdir -p .bugs/bugs
  run_hg b list
  (( status != 0 ))
}

@test "bad-db malformed" {
  mkdir -p .bugs
  echo "foo | bar" > .bugs/bugs
  run_hg b list
  (( status != 0 ))
}

@test "bad-command" {
  run_hg b foo
  (( status != 0 ))
  [[ "$output" =~ No\ such\ command ]]

  run_hg b ''
  (( status != 0 ))
  [[ "$output" =~ ambiguous ]]
  run_hg b re
  (( status != 0 ))
  [[ "$output" =~ ambiguous ]]
}

@test "bad-input" {
  hg b add some bug
  run_hg b assign -f 7 'foo|bar'
  (( status != 0 ))
  [[ "$output" =~ Invalid\ input ]]
}

@test "bad-prefix-args" {
  # titles hash to a common prefix b7
  hg b add some bug 8
  hg b add some bug 9
  hg b list -a

  run_hg b id
  (( status != 0 ))
  [[ "$output" =~ provide\ an\ issue ]]

  run_hg b id b7
  (( status != 0 ))
  [[ "$output" =~ ambiguous ]]

  run_hg b id c
  (( status != 0 ))
  [[ "$output" =~ could\ not\ be\ found ]]
}

@test "bad-user-args" {
  hg b add some bug
  hg b add another bug
  hg b assign 7 -f UserA
  hg b assign 8 -f UserB

  run_hg b list -o ''
  (( status != 0 ))
  [[ "$output" =~ more\ than\ one ]]

  run_hg b list -o use
  (( status != 0 ))
  [[ "$output" =~ more\ than\ one ]]

  run_hg b list -o foo
  (( status != 0 ))
  [[ "$output" =~ did\ not\ match ]]
}

@test "bad-readonly-cmd" {
  hg b add some bug
  hg --config ui.username=username commit -m "commit"
  run_hg b --rev tip add some bug
  (( status != 0 ))
  [[ "$output" =~ not\ a\ supported\ flag ]]
}
