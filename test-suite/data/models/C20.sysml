package C20 {
    private import ScalarValues::*;

    attribute def Alarm;
    port def AlarmPort;
    part def Display;
    action def Notify;

    // kinds of action, in an action def body
    action def Supervise {
        in alarm : Alarm;
        in alarmPort : AlarmPort;
        in display : Display;
        attribute count : Integer;

        action sendVia send alarm via alarmPort;
        action sendTo send alarm to display;
        action acceptVia accept sig : Alarm via alarmPort;
        action assignCount assign count := 1;
        perform action performNotify : Notify;
        action ifAct if count > 0 { action whenPositive; }
        action whileAct while count < 3 { action step; }
        action forAct for i : Integer in (1, 2, 3) { action each; }
    }

    // the same kinds, nested in an action usage owned by a part def
    part def Monitor {
        ref alarm : Alarm;
        port alarmPort : AlarmPort;
        part display : Display;
        attribute count : Integer;
        action supervise {
            action sendVia send alarm via alarmPort;
            action sendTo send alarm to display;
            action acceptVia accept sig : Alarm via alarmPort;
            action assignCount assign count := 1;
            perform action performNotify : Notify;
            action ifAct if count > 0 { action whenPositive; }
            action whileAct while count < 3 { action step; }
            action forAct for i : Integer in (1, 2, 3) { action each; }
        }
    }
    part monitor : Monitor;     // read through a typing usage: monitor.supervise
}
