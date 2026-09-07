_baton()
{
  local cur="${COMP_WORDS[COMP_CWORD]}"
  local cmds="init clis models status model attach set list select sidecar doctor sessions detach claude claude_code codex agent cursor agentx"
  if [[ ${COMP_CWORD} -eq 1 ]]; then
    COMPREPLY=( $(compgen -W "${cmds}" -- "${cur}") )
    return
  fi
  if [[ ${COMP_WORDS[1]} == clis ]]; then
    COMPREPLY=( $(compgen -W "list enable disable set refresh claude_code codex cursor" -- "${cur}") )
  fi
}
complete -F _baton baton
