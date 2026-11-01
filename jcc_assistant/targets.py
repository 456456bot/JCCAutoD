import threading

from .settings import validate_targets


class TargetList:
    """Authoritative live target list; membership and click dispatch are serialized."""

    def __init__(self):
        self._lock = threading.RLock()
        self._names = ()
        self._revision = 0
        self._selection_epoch = 0
        self._activations = {}
        self._work = threading.Event()
        self._rules = {}
        self.default_rule = 0

    def rules(self):
        with self._lock:
            return {name: self._rules.get(name, self.default_rule) for name in self._names}

    def set_rule(self, name, rule):
        if rule not in (0, 2, 3):
            raise ValueError("停止条件只能为持续购买、二星或三星")
        with self._lock:
            if name in self._names:
                self._rules[name] = rule
                self._revision += 1
                self._work.set()

    def edit(self, old_name, name, rule):
        name = validate_targets([name])[0]
        if type(rule) is not int or rule not in (0, 2, 3):
            raise ValueError("停止条件格式错误")
        with self._lock:
            names = list(self._names)
            if old_name and old_name not in names:
                raise ValueError("原目标已被移除，请关闭窗口后重新新增。")
            if name != old_name and name in names:
                raise ValueError("这张牌已在目标列表中。")
            if old_name:
                names[names.index(old_name)] = name
            else:
                names.append(name)
            rules = self.rules()
            if old_name:
                rules.pop(old_name, None)
            rules[name] = rule
            self.replace(names, rules)

    def remove(self, names):
        with self._lock:
            self.replace([name for name in self._names if name not in names])

    def snapshot(self):
        with self._lock:
            return self._revision, self._names

    def replace(self, names, rules=None):
        names = tuple(validate_targets(names))
        if rules is not None:
            from .settings import validate_stop_rules

            rules = validate_stop_rules(rules, names)
        with self._lock:
            if names != self._names or rules is not None:
                self._names = names
                self._rules = {
                    name: (rules or {}).get(name, self._rules.get(name, self.default_rule))
                    for name in names
                }
                self._revision += 1
                self._activations = {
                    name: self._activations.get(name, self._revision) for name in names
                }
                self._work.set()

    def wake(self):
        self._work.set()

    def wait(self, timeout=0.1):
        self._work.wait(timeout)
        self._work.clear()

    def activation_snapshot(self):
        with self._lock:
            return self._revision, self._names, dict(self._activations)

    def add(self, name):
        name = validate_targets([name])[0]
        with self._lock:
            if name in self._names:
                return False
            self._names += (name,)
            self._revision += 1
            self._activations[name] = self._revision
            self._rules[name] = self.default_rule
            self._work.set()
            return True

    def clear(self):
        with self._lock:
            self._selection_epoch += 1
            self.replace([])
            self._work.set()

    def selection_epoch(self):
        with self._lock:
            return self._selection_epoch

    def add_selection(self, name, epoch):
        with self._lock:
            if epoch != self._selection_epoch:
                return None
            return self.add(name)

    def detail_selection(self, name, action, epoch):
        with self._lock:
            if epoch != self._selection_epoch:
                return None
            if action == "add":
                added = self.add(name)
                if added:
                    self._rules[name] = 0
                return added
            if action == "remove":
                existed = name in self._names
                self.remove({name})
                return existed
            raise ValueError("未知目标操作")

    def dispatch(self, name, action):
        return self.dispatch_purchase(name, action)[0]

    def dispatch_if_nonempty(self, action):
        with self._lock:
            if not self._names:
                return False
            action()
            return True

    def dispatch_purchase(self, name, action, upgrade=0):
        with self._lock:
            if name not in self._names:
                return False, False
            action()
            rule = self._rules.get(name, self.default_rule)
            removed = bool(rule and upgrade >= rule and name in self._names)
            if removed:
                self.replace([n for n in self._names if n != name])
            return True, removed
