package giftwrap

import "testing"

func TestAC1AddsWrappingFee(t *testing.T) {
	if got := Total(1000, true); got != 1300 {
		t.Fatalf("got %d, want 1300", got)
	}
}
