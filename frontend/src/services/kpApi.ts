// frontend/src/api/kpApi.ts
import API_BASE_URL from '../config/api';

export interface KnowledgePoint {
    mermaid_id: string;
    name: string;
    level: 'root' | 'big_idea' | 'core_concept' | 'sub_technique';
    description: string;
    confidence: number;
    parent_mermaid_id: string | null;
}

export interface KPRelationship {
    from: string;
    to: string;
    type: 'prerequisite' | 'composition' | 'contrast' | 'extension';
}

export interface KPMap {
    knowledge_points: KnowledgePoint[];
    relationships: KPRelationship[];
    mermaid_graph: string;
    version?: number;
}

export interface ExtractKPResponse {
    status: 'success' | 'exists' | 'error';
    message: string;
    kp_map?: KPMap;
    error?: string;
}

export interface GetKPResponse {
    unique_content_id: number;
    teacher_id: number;
    version: number;
    kp_map: KPMap;
}

/**
 * Extract knowledge points from a document
 */
export async function extractKP(
    unique_content_id: number,
    teacher_id: number,
    force_regenerate: boolean = false
): Promise<ExtractKPResponse> {
    const response = await fetch(`${API_BASE_URL}/api/kp/extract`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            unique_content_id,
            teacher_id,
            force_regenerate
        })
    });

    if (!response.ok) {
        throw new Error(`KP extraction failed: ${response.statusText}`);
    }

    return await response.json();
}

/**
 * Get existing KP map for a document
 */
export async function getKPMap(
    unique_content_id: number,
    teacher_id: number,
    version?: number
): Promise<GetKPResponse> {
    const url = version
        ? `${API_BASE_URL}/api/kp/${unique_content_id}/${teacher_id}?version=${version}`
        : `${API_BASE_URL}/api/kp/${unique_content_id}/${teacher_id}`;

    const response = await fetch(url);

    // Handle 204 No Content (No matching KPs found, but not an error)
    if (response.status === 204) {
        throw new Error('NO_KP_FOUND');
    }

    if (!response.ok) {
        if (response.status === 404) {
            throw new Error('NO_KP_FOUND');
        }
        throw new Error(`Failed to get KP map: ${response.statusText}`);
    }

    return await response.json();
}

// ==================== Unit KP CRUD ====================

export interface UnitKP {
    id: number;
    name: string;
    source_type: 'extracted' | 'manual';
    source_name: string;
    source_id?: number | null;
    unit_id: number;
}

export interface PromoteKPResponse {
    status: string;
    promoted_count: number;
    already_existed_count: number;
    knowledge_points: Array<UnitKP & { already_existed?: boolean }>;
}

/** Get all confirmed KPs for a unit */
export async function getUnitKPs(courseId: number, unitId: number): Promise<UnitKP[]> {
    const response = await fetch(`${API_BASE_URL}/api/courses/${courseId}/units/${unitId}/kps`);
    if (!response.ok) throw new Error('Failed to load unit KPs');
    return response.json();
}

/** Manually add a KP to a unit */
export async function createUnitKP(courseId: number, unitId: number, name: string): Promise<UnitKP> {
    const response = await fetch(`${API_BASE_URL}/api/courses/${courseId}/units/${unitId}/kps`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
    });
    if (response.status === 409) {
        const data = await response.json();
        throw new Error(data.detail || '知識點名稱已存在');
    }
    if (!response.ok) throw new Error('Failed to create KP');
    return response.json();
}

/** Rename a unit KP */
export async function updateUnitKP(
    courseId: number, unitId: number, kpId: number, name: string
): Promise<{ id: number; name: string }> {
    const response = await fetch(`${API_BASE_URL}/api/courses/${courseId}/units/${unitId}/kps/${kpId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
    });
    if (response.status === 409) {
        const data = await response.json();
        throw new Error(data.detail || '知識點名稱已存在');
    }
    if (!response.ok) throw new Error('Failed to update KP');
    return response.json();
}

/** Delete a unit KP. Returns linked_questions so the caller can show a warning. */
export async function deleteUnitKP(
    courseId: number, unitId: number, kpId: number
): Promise<{ deleted_kp_id: number; name: string; linked_questions: number }> {
    const response = await fetch(`${API_BASE_URL}/api/courses/${courseId}/units/${unitId}/kps/${kpId}`, {
        method: 'DELETE',
    });
    if (!response.ok) throw new Error('Failed to delete KP');
    return response.json();
}

/** Promote selected extracted KP names into the unit's confirmed knowledge_points table */
export async function promoteKPs(
    uniqueContentId: number,
    kpNames: string[],
    unitId: number,
    courseId: number
): Promise<PromoteKPResponse> {
    const response = await fetch(`${API_BASE_URL}/api/kp/promote`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            unique_content_id: uniqueContentId,
            kp_names: kpNames,
            unit_id: unitId,
            course_id: courseId,
        }),
    });
    if (!response.ok) throw new Error('KP promotion failed');
    return response.json();
}

/** Get question counts for specific KP names */
export async function getKPStats(courseId: number | string, kpNames: string[]): Promise<Record<string, number>> {
    const params = new URLSearchParams({ kp_names: kpNames.join(',') });
    const response = await fetch(`${API_BASE_URL}/api/courses/${courseId}/question-bank/kp-stats?${params.toString()}`);
    if (!response.ok) throw new Error('Failed to load KP stats');
    return response.json();
}
