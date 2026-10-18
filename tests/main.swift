import Foundation

private var checked = 0

private func expect(_ condition: @autoclosure () -> Bool, _ message: String) {
    checked += 1
    guard condition() else {
        fputs("FAIL: \(message)\n", stderr)
        exit(1)
    }
}

private func preserves(_ active: Bool, _ cached: String?, _ observed: String?) -> Bool {
    BattlegroundsReconnectPolicy.shouldPreserveSession(
        activeBattlegroundsMatch: active,
        cachedGameHandle: cached,
        observedGameHandle: observed)
}

// These handles are synthetic policy cases, not values recovered from the
// user's logs. Unknown identity must never be treated as positive evidence.
expect(preserves(true, "501", "501"), "same active match")
expect(preserves(true, "501", "501"), "second reconnect in same match")
expect(preserves(true, "501", "501"), "third reconnect in same match")
expect(!preserves(true, "501", "502"), "different match during scene transition")
expect(!preserves(false, "501", "501"), "ended/menu/non-Battlegrounds match")
expect(!preserves(true, nil, "501"), "tracker started mid-match without cached identity")
expect(!preserves(true, "501", nil), "mirror temporarily unavailable")
expect(!preserves(true, nil, nil), "no identity evidence")
expect(!preserves(true, "0", "0"), "zero is not a valid game handle")
expect(!preserves(true, "-1", "-1"), "negative handle")
expect(!preserves(true, "unknown", "unknown"), "unparsed handle")
expect(!preserves(true, "501", "0"), "zero observed after valid cached identity")
expect(!preserves(true, "18446744073709551616", "18446744073709551616"), "numeric overflow")
expect(preserves(true, "18446744073709551615", "18446744073709551615"), "full-width positive handle")

print("PASS: \(checked) production identity-policy assertions")
