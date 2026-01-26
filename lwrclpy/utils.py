import importlib
import types


TOPIC_PREFIX = "rt/"
SERVICE_REQUEST_PREFIX = "rq/"
SERVICE_RESPONSE_PREFIX = "rr/"
ACTION_PREFIX = "ra/"


def _normalize_namespace(ns: str) -> str:
    """Normalize namespace per ROS 2 rules (leading slash, no trailing slash except root)."""
    if not ns:
        return ""
    ns = "/" + ns.lstrip("/")
    if len(ns) > 1 and ns.endswith("/"):
        ns = ns.rstrip("/")
    return ns


def _join_with_namespace(ns: str, name: str) -> str:
    ns = ns.rstrip("/")
    name = name.lstrip("/")
    if not ns:
        return "/" + name if name else "/"
    if not name:
        return ns
    return ns + "/" + name


def resolve_name(name: str, namespace: str, node_name: str) -> str:
    """
    Resolve ROS graph names (topics/services) following ROS 2 name resolution rules:
      - absolute: /foo stays /foo
      - relative: foo -> <namespace>/foo
      - private: ~foo -> <namespace>/<node_name>/foo
    Reference: https://design.ros2.org/articles/topic_and_service_names.html
    Returns an absolute name starting with "/".
    """
    if not name:
        return _normalize_namespace(namespace) or "/"
    if name.startswith("~"):
        ns = _normalize_namespace(namespace)
        base = _join_with_namespace(ns or "/", node_name)
        return _join_with_namespace(base, name[1:])
    if name.startswith("/"):
        cleaned = name.lstrip("/")
        return "/" + cleaned
    ns = _normalize_namespace(namespace)
    return _join_with_namespace(ns or "/", name)


def resolve_generated_type(obj):
    """
    fastddsgen -python 生成物を指す `obj` (モジュール or クラス) から
    (module, msg_cls, pubsub_cls) を返す。

    期待する命名:
      - モジュールに <Name> クラスと <Name>PubSubType が同居
      - もしくはクラスを直接渡す（この場合は pubsub 名は <ClassName>PubSubType）
    """
    # 1) 基底モジュールを取得
    if isinstance(obj, type):  # クラスが渡された
        msg_cls = obj
        mod = importlib.import_module(obj.__module__)
        pubsub_name = obj.__name__ + "PubSubType"
        pubsub_cls = getattr(mod, pubsub_name, None)
        if pubsub_cls is None:
            # 安全側：モジュール内を総当たり
            pubsub_cls = _find_first_pubsub(mod, prefer=obj.__name__)
        if pubsub_cls is None:
            raise RuntimeError(
                f"PubSubType not found (expected '{pubsub_name}') in module '{mod.__name__}'"
            )
        return mod, msg_cls, pubsub_cls

    # モジュールが渡された場合
    if isinstance(obj, types.ModuleType):
        mod = obj
    else:
        # __init__.py の動的再エクスポートで来る可能性に備え、__module__ 経由で辿る
        mod = importlib.import_module(obj.__module__)

    # 2) モジュール内から候補抽出
    pubsub_cls, msg_cls = _pair_from_module(mod)
    if pubsub_cls is None or msg_cls is None:
        raise RuntimeError("Failed to resolve generated type (module/class mismatch)")
    return mod, msg_cls, pubsub_cls


def resolve_service_type(obj):
    """
    推定ルール:
      - rclpy 互換: <Srv>.Request / <Srv>.Response を持つ
      - fastddsgen 出力: <Srv>_request / <Srv>_response などがモジュールに居る
    戻り値: (request_cls, response_cls, request_pubsub_cls, response_pubsub_cls)
    """
    mod = None
    # rclpy スタイルのクラス (Request/Response 属性)
    if isinstance(obj, type):
        mod = importlib.import_module(obj.__module__)
        req = getattr(obj, "Request", None)
        res = getattr(obj, "Response", None)
    else:
        mod = importlib.import_module(obj.__module__)
        req = getattr(obj, "Request", None)
        res = getattr(obj, "Response", None)
    # fastddsgen 名寄せ (Foo_Request / Foo_Response)
    if req is None:
        req = getattr(mod, f"{obj.__name__}Request", None) if isinstance(obj, type) else None
    if res is None:
        res = getattr(mod, f"{obj.__name__}Response", None) if isinstance(obj, type) else None

    # fallback: scan module for *Request/*Response
    if req is None or res is None:
        for name in dir(mod):
            if req is None and name.lower().endswith("request"):
                cand = getattr(mod, name)
                if isinstance(cand, type):
                    req = cand
            if res is None and name.lower().endswith("response"):
                cand = getattr(mod, name)
                if isinstance(cand, type):
                    res = cand
    if req is None or res is None:
        raise RuntimeError("Could not resolve service Request/Response classes")

    _mod, req_cls, req_pubsub = resolve_generated_type(req)
    _mod, res_cls, res_pubsub = resolve_generated_type(res)
    return req_cls, res_cls, req_pubsub, res_pubsub


def _get_cancel_goal_types():
    """
    Get CancelGoal Request/Response types from action_msgs.
    Handles both rclpy-style (CancelGoal.Request) and fastddsgen-style (CancelGoal_Request).
    """
    try:
        import action_msgs.srv.CancelGoal as cg_mod
        # Try rclpy-style first
        cancel_goal_srv = getattr(cg_mod, "CancelGoal", None)
        if cancel_goal_srv is not None:
            req = getattr(cancel_goal_srv, "Request", None)
            res = getattr(cancel_goal_srv, "Response", None)
            if req is not None and res is not None:
                return req, res
        # Try fastddsgen-style
        req = getattr(cg_mod, "CancelGoal_Request", None)
        res = getattr(cg_mod, "CancelGoal_Response", None)
        if req is not None and res is not None:
            return req, res
    except ImportError:
        pass
    return None, None


def resolve_action_type(action_type):
    """
    Resolve ROS2-style action generated classes.
    Supports both rclpy-style nested classes (Goal, Result, SendGoal.Request) and
    fastddsgen-style flat classes (<ActionName>_Goal, <ActionName>_SendGoal_Request).
    
    For rclpy-style:
      Expects attributes: Goal, Result, Feedback,
        SendGoal (with Request/Response),
        GetResult (with Request/Response),
        FeedbackMessage,
        CancelGoal (action_msgs/srv/CancelGoal)
    
    For fastddsgen-style:
      Expects attributes: <ActionName>_Goal, <ActionName>_Result, <ActionName>_Feedback,
        <ActionName>_SendGoal_Request, <ActionName>_SendGoal_Response,
        <ActionName>_GetResult_Request, <ActionName>_GetResult_Response,
        <ActionName>_FeedbackMessage
    """
    # Determine action name from module or type
    action_name = None
    if isinstance(action_type, type):
        action_name = action_type.__name__
    elif hasattr(action_type, "__name__"):
        # Module: extract base name from module path
        mod_name = action_type.__name__
        action_name = mod_name.split(".")[-1] if mod_name else None
    
    # Try rclpy-style first
    goal_cls = getattr(action_type, "Goal", None)
    result_cls = getattr(action_type, "Result", None)
    feedback_cls = getattr(action_type, "Feedback", None)
    send_goal = getattr(action_type, "SendGoal", None)
    get_result = getattr(action_type, "GetResult", None)
    feedback_msg_cls = getattr(action_type, "FeedbackMessage", None)
    cancel_srv = getattr(action_type, "CancelGoal", None)

    # If rclpy-style is available
    if all([goal_cls, result_cls, feedback_cls, send_goal, get_result, feedback_msg_cls]):
        send_goal_req = getattr(send_goal, "Request", None)
        send_goal_res = getattr(send_goal, "Response", None)
        get_result_req = getattr(get_result, "Request", None)
        get_result_res = getattr(get_result, "Response", None)
        if all([send_goal_req, send_goal_res, get_result_req, get_result_res]):
            # Resolve CancelGoal
            cancel_req = None
            cancel_res = None
            if cancel_srv is not None:
                cancel_req = getattr(cancel_srv, "Request", None)
                cancel_res = getattr(cancel_srv, "Response", None)
            # If CancelGoal not found from action type, try action_msgs
            if cancel_req is None or cancel_res is None:
                cancel_req, cancel_res = _get_cancel_goal_types()
            if cancel_req is None or cancel_res is None:
                raise RuntimeError("CancelGoal Request/Response not found")
            return {
                "goal": goal_cls,
                "result": result_cls,
                "feedback": feedback_cls,
                "send_goal_req": send_goal_req,
                "send_goal_res": send_goal_res,
                "get_result_req": get_result_req,
                "get_result_res": get_result_res,
                "feedback_msg": feedback_msg_cls,
                "cancel_req": cancel_req,
                "cancel_res": cancel_res,
            }
    
    # Try fastddsgen-style (flat class names)
    if action_name:
        goal_cls = getattr(action_type, f"{action_name}_Goal", None)
        result_cls = getattr(action_type, f"{action_name}_Result", None)
        feedback_cls = getattr(action_type, f"{action_name}_Feedback", None)
        feedback_msg_cls = getattr(action_type, f"{action_name}_FeedbackMessage", None)
        send_goal_req = getattr(action_type, f"{action_name}_SendGoal_Request", None)
        send_goal_res = getattr(action_type, f"{action_name}_SendGoal_Response", None)
        get_result_req = getattr(action_type, f"{action_name}_GetResult_Request", None)
        get_result_res = getattr(action_type, f"{action_name}_GetResult_Response", None)
        
        if all([goal_cls, result_cls, feedback_cls, feedback_msg_cls,
                send_goal_req, send_goal_res, get_result_req, get_result_res]):
            # Get CancelGoal from action_msgs
            cancel_req, cancel_res = _get_cancel_goal_types()
            if cancel_req is None or cancel_res is None:
                raise RuntimeError("CancelGoal Request/Response not found in action_msgs")
            return {
                "goal": goal_cls,
                "result": result_cls,
                "feedback": feedback_cls,
                "send_goal_req": send_goal_req,
                "send_goal_res": send_goal_res,
                "get_result_req": get_result_req,
                "get_result_res": get_result_res,
                "feedback_msg": feedback_msg_cls,
                "cancel_req": cancel_req,
                "cancel_res": cancel_res,
            }
    
    raise RuntimeError(
        f"Action type missing required classes. "
        f"Expected rclpy-style (Goal/Result/Feedback/SendGoal/GetResult/FeedbackMessage) or "
        f"fastddsgen-style ({action_name}_Goal/{action_name}_Result/etc)"
    )


def _find_first_pubsub(mod, prefer: str | None = None):
    # <Name>PubSubType を優先
    if prefer:
        cand = prefer + "PubSubType"
        if hasattr(mod, cand):
            return getattr(mod, cand)
    # それ以外の *PubSubType でも可
    for n in dir(mod):
        if n.endswith("PubSubType"):
            return getattr(mod, n)
    return None


def _pair_from_module(mod):
    pubsub = _find_first_pubsub(mod)
    if pubsub is None:
        return None, None
    # たとえば StringPubSubType -> String を優先
    base = pubsub.__name__.removesuffix("PubSubType")
    msg_cls = getattr(mod, base, None)
    if isinstance(msg_cls, type):
        return pubsub, msg_cls
    # フォールバック：最初に見つかったクラス
    for n in dir(mod):
        obj = getattr(mod, n)
        if isinstance(obj, type) and not n.endswith("PubSubType"):
            return pubsub, obj
    return pubsub, None


def get_or_create_topic(participant, name: str, type_name: str):
    """
    Reuse an existing Topic on the participant when the name is already registered.
    Returns (topic, owned) where owned=False means an existing Topic was reused.
    """
    import fastdds  # local import to avoid mandatory dependency at import-time

    # Try to reuse an existing Topic instance first
    try:
        duration = fastdds.Duration_t()
        duration.seconds = 0
        duration.nanosec = 0
        existing_topic = participant.find_topic(name, duration)
    except Exception:
        existing_topic = None
    if existing_topic is not None:
        # Ensure type matches
        try:
            existing_type = existing_topic.get_type_name()
            if existing_type and existing_type != type_name:
                raise RuntimeError(
                    f"Topic '{name}' already exists with type '{existing_type}' (requested '{type_name}')"
                )
            return existing_topic, False
        except Exception:
            pass

    tq = fastdds.TopicQos()
    participant.get_default_topic_qos(tq)
    topic_obj = participant.create_topic(name, type_name, tq)
    if topic_obj is None:
        raise RuntimeError(f"Failed to create topic '{name}'")
    return topic_obj, True
