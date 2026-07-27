/**
 * Utility to track active time spent on a page or section, 
 * automatically pausing when the window is blurred, document is hidden,
 * or the user is idle.
 */
export class ActiveTimer {
    private accumulatedActiveTime: number = 0;
    private lastFocusTime: number = 0;
    private lastActivityTime: number = 0;
    private isRunning: boolean = false;
    private isPausedForVisibility: boolean = false;
    private isPausedManually: boolean = false;
    private IDLE_THRESHOLD: number = 60000; // 60 seconds

    constructor() {
        this.handleVisibilityChange = this.handleVisibilityChange.bind(this);
        this.handleFocus = this.handleFocus.bind(this);
        this.handleBlur = this.handleBlur.bind(this);
        this.updateActivity = this.updateActivity.bind(this);
    }

    start() {
        if (this.isRunning) return;
        this.isRunning = true;
        const now = Date.now();
        this.lastFocusTime = now;
        this.lastActivityTime = now;
        this.accumulatedActiveTime = 0;
        this.isPausedForVisibility = false;
        this.isPausedManually = false;

        window.addEventListener('visibilitychange', this.handleVisibilityChange);
        window.addEventListener('focus', this.handleFocus);
        window.addEventListener('blur', this.handleBlur);

        // Activity listeners
        window.addEventListener('mousemove', this.updateActivity);
        window.addEventListener('keydown', this.updateActivity);
        window.addEventListener('click', this.updateActivity);
        window.addEventListener('scroll', this.updateActivity);
    }

    stop(): number {
        if (!this.isRunning) return 0;
        const total = this.getElapsedSeconds();
        this.isRunning = false;
        this.isPausedForVisibility = false;
        this.isPausedManually = false;

        window.removeEventListener('visibilitychange', this.handleVisibilityChange);
        window.removeEventListener('focus', this.handleFocus);
        window.removeEventListener('blur', this.handleBlur);

        window.removeEventListener('mousemove', this.updateActivity);
        window.removeEventListener('keydown', this.updateActivity);
        window.removeEventListener('click', this.updateActivity);
        window.removeEventListener('scroll', this.updateActivity);

        return total;
    }

    private updateActivity() {
        if (!this.isRunning) return;

        const now = Date.now();
        const wasIdle = (now - this.lastActivityTime) > this.IDLE_THRESHOLD;

        if (wasIdle) {
            // "Close" the previous active segment that ended at lastActivityTime
            if (!this.isPausedForVisibility && !this.isPausedManually) {
                const contribution = Math.max(0, this.lastActivityTime - this.lastFocusTime);
                this.accumulatedActiveTime += contribution;
            }
            // Start a new segment from now
            this.lastFocusTime = now;
        }

        this.lastActivityTime = now;
    }

    getElapsedSeconds(): number {
        if (!this.isRunning) return this.accumulatedActiveTime / 1000;

        let sessionActive = 0;
        const now = Date.now();
        const isIdle = (now - this.lastActivityTime) > this.IDLE_THRESHOLD;

        if (!this.isPausedForVisibility && !this.isPausedManually && !document.hidden && document.hasFocus()) {
            // If idle, we only count up to the last known activity
            const effectiveNow = isIdle ? this.lastActivityTime : now;
            sessionActive = Math.max(0, effectiveNow - this.lastFocusTime);
        }

        return (this.accumulatedActiveTime + sessionActive) / 1000;
    }

    public manualPause() {
        if (!this.isRunning || this.isPausedManually) return;

        const now = Date.now();
        const isIdle = (now - this.lastActivityTime) > this.IDLE_THRESHOLD;
        const effectiveNow = isIdle ? this.lastActivityTime : now;

        this.accumulatedActiveTime += Math.max(0, effectiveNow - this.lastFocusTime);
        this.isPausedManually = true;
    }

    public manualResume() {
        if (!this.isRunning || !this.isPausedManually) return;
        const now = Date.now();
        this.lastFocusTime = now;
        this.lastActivityTime = now;
        this.isPausedManually = false;
    }

    private handleVisibilityChange() {
        if (document.hidden) {
            this.pause();
        } else {
            this.resume();
        }
    }

    private handleFocus() {
        this.resume();
    }

    private handleBlur() {
        this.pause();
    }

    private pause() {
        if (!this.isRunning || this.isPausedForVisibility || this.isPausedManually) return;

        const now = Date.now();
        const isIdle = (now - this.lastActivityTime) > this.IDLE_THRESHOLD;
        const effectiveNow = isIdle ? this.lastActivityTime : now;

        this.accumulatedActiveTime += Math.max(0, effectiveNow - this.lastFocusTime);
        this.isPausedForVisibility = true;
    }

    private resume() {
        if (!this.isRunning || !this.isPausedForVisibility || this.isPausedManually) return;
        if (document.hidden || !document.hasFocus()) return;
        const now = Date.now();
        this.lastFocusTime = now;
        this.lastActivityTime = now;
        this.isPausedForVisibility = false;
    }
}
