package dev.openguard.scan;

import static org.junit.jupiter.api.Assertions.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class ResourceProfileDraftTest {
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final String SHA = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
    @Test void model_maps_to_pending_candidate_without_license_conclusion() throws Exception {
        var draft = ResourceProfileDraft.fromHuggingFace(JSON.readTree("{\"id\":\"acme/demo\",\"sha\":\"0123456789abcdef0123456789abcdef01234567\",\"private\":false,\"gated\":false,\"cardData\":{\"license\":\"apache-2.0\"}}"), "model", "fixtures/model.json", SHA, Instant.parse("2026-09-19T00:00:00Z"));
        assertEquals("https://huggingface.co/acme/demo", draft.canonicalUrl()); assertEquals("ungated", draft.accessGate());
        assertNull(draft.toPendingP0Candidate().licenseExpressionId()); assertEquals("pending", draft.toPendingP0Candidate().authorizationStatus());
    }
    @Test void dataset_auto_gate_and_license_conflict_degrade() throws Exception {
        var draft = ResourceProfileDraft.fromHuggingFace(JSON.readTree("{\"id\":\"acme/data\",\"gated\":\"auto\",\"license\":\"mit\",\"cardData\":{\"license\":\"apache-2.0\"}}"), "dataset", "fixtures/data.json", SHA, Instant.EPOCH);
        assertEquals("unknown", draft.accessGate()); assertNull(draft.declaredLicense()); assertTrue(draft.diagnostics().contains("conflicting_declared_license"));
    }
    @Test void invalid_identity_fails_closed() throws Exception { assertThrows(IllegalArgumentException.class, () -> ResourceProfileDraft.fromHuggingFace(JSON.readTree("{}"), "model", "fixtures/no-id.json", SHA, Instant.EPOCH)); }
}
