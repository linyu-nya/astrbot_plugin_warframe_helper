import inspect


async def _await_if_needed(value):
    if inspect.isawaitable(value):
        return await value
    return value


async def _reply(event, text):
    return await _await_if_needed(event.plain_result(text))


def _field(value, name, default=None):
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


async def wfmap(event, args, mapper):
    if not event.is_admin():
        return await _reply(event, "无权限：仅管理员可执行此操作")
    if len(args) < 2:
        return await _reply(event, "用法：/wfmap 别名 全称")

    alias, full_name = args[0], " ".join(args[1:])
    try:
        result = await _await_if_needed(
            mapper.upsert_user_alias(alias=alias, full_name=full_name)
        )
        normalized_alias, normalized_full_name = result
        return await _reply(
            event, f"已添加映射：{normalized_alias} -> {normalized_full_name}"
        )
    except Exception as exc:
        return await _reply(event, f"操作失败：{exc!s}")


async def wfmapdel(event, args, mapper):
    if not event.is_admin():
        return await _reply(event, "无权限：仅管理员可执行此操作")
    if len(args) != 1:
        return await _reply(event, "用法：/wfmapdel 别名")

    alias = args[0]
    try:
        status = await _await_if_needed(mapper.delete_user_alias(alias))
        if status == "deleted":
            resolved = await _await_if_needed(mapper.resolve_alias_only(alias))
            restored = _field(resolved, "matched", None)
            if restored is None:
                restored = bool(resolved)
            if restored:
                name = _field(resolved, "canonical_full_name", resolved)
                return await _reply(event, f"已删除映射：{alias} -> {name}（已恢复内置映射）")
            return await _reply(event, f"已删除映射：{alias}")
        if status == "builtin_only":
            return await _reply(event, f"该别名仅有内置映射，未删除用户映射：{alias}")
        if status == "not_found":
            return await _reply(event, f"未找到用户映射：{alias}")
        return await _reply(event, f"操作失败：未知删除状态 {status}")
    except Exception as exc:
        return await _reply(event, f"操作失败：{exc!s}")


async def wfmapq(event, args, mapper):
    if not args:
        return await _reply(event, "用法：/wfmapq 全称")

    full_name = " ".join(args)
    try:
        entries = await _await_if_needed(mapper.find_effective_aliases(full_name))
        if not entries:
            return await _reply(event, f"未找到全称‘{full_name}’的有效别名")
        source_labels = {
            "builtin": "内置",
            "base": "内置",
            "riven_weapon": "紫卡武器",
            "user": "用户自定义",
        }
        lines = [f"{full_name} 的别名："]
        for entry in entries:
            source = _field(entry, "source", "")
            label = source_labels.get(source, source or "未知")
            lines.append(f"- {_field(entry, 'alias', '')}（{label}）")
        return await _reply(event, "\n".join(lines))
    except Exception as exc:
        return await _reply(event, f"操作失败：{exc!s}")


async def compatible_alias_add(event, args, mapper):
    return await wfmap(event, args, mapper)
