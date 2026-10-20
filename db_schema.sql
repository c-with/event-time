-- Reference DDL generated from models.py; init-db applies the same metadata.
-- Do not hand-edit independently from models.py.

CREATE TABLE app_users (
	id VARCHAR(36) NOT NULL, 
	username VARCHAR(120) NOT NULL, 
	display_name VARCHAR(160) NOT NULL, 
	password_hash VARCHAR(256) NOT NULL, 
	active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (username)
);

CREATE TABLE clients (
	id VARCHAR(36) NOT NULL, 
	name VARCHAR(240) NOT NULL, 
	aliases TEXT NOT NULL, 
	notes TEXT NOT NULL, 
	revision INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_clients_name ON clients (name);

CREATE TABLE suppliers (
	id VARCHAR(36) NOT NULL, 
	name VARCHAR(240) NOT NULL, 
	service_category VARCHAR(160) NOT NULL, 
	notes TEXT NOT NULL, 
	verified_at TIMESTAMP WITH TIME ZONE, 
	revision INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_suppliers_name ON suppliers (name);

CREATE TABLE venues (
	id VARCHAR(36) NOT NULL, 
	name VARCHAR(240) NOT NULL, 
	address TEXT NOT NULL, 
	notes TEXT NOT NULL, 
	verified_status VARCHAR(60) NOT NULL, 
	verified_at TIMESTAMP WITH TIME ZONE, 
	verified_by VARCHAR(160) NOT NULL, 
	revision INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_venues_name ON venues (name);

CREATE TABLE documents (
	id VARCHAR(36) NOT NULL, 
	series_id VARCHAR(36) NOT NULL, 
	version_no INTEGER NOT NULL, 
	previous_document_id VARCHAR(36) NOT NULL, 
	original_name VARCHAR(300) NOT NULL, 
	stored_name VARCHAR(300) NOT NULL, 
	mime_type VARCHAR(160) NOT NULL, 
	category VARCHAR(100) NOT NULL, 
	sha256 VARCHAR(64) NOT NULL, 
	storage_path TEXT NOT NULL, 
	optimized_path TEXT NOT NULL, 
	thumbnail_path TEXT NOT NULL, 
	original_size BIGINT NOT NULL, 
	stored_size BIGINT NOT NULL, 
	is_official BOOLEAN NOT NULL, 
	processing_status VARCHAR(60) NOT NULL, 
	notes TEXT NOT NULL, 
	uploaded_by VARCHAR(160) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_document_series_version UNIQUE (series_id, version_no)
);

CREATE INDEX ix_documents_sha256 ON documents (sha256);

CREATE INDEX ix_documents_created_at ON documents (created_at);

CREATE INDEX ix_documents_series_id ON documents (series_id);

CREATE TABLE change_requests (
	id VARCHAR(36) NOT NULL, 
	entity_type VARCHAR(60) NOT NULL, 
	entity_id VARCHAR(36) NOT NULL, 
	field_path VARCHAR(120) NOT NULL, 
	old_value JSON, 
	new_value JSON, 
	base_revision INTEGER NOT NULL, 
	source_ref TEXT NOT NULL, 
	source_text TEXT NOT NULL, 
	proposed_by VARCHAR(160) NOT NULL, 
	status VARCHAR(40) NOT NULL, 
	confirmed_by VARCHAR(160) NOT NULL, 
	confirmed_at TIMESTAMP WITH TIME ZONE, 
	resolution_note TEXT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_change_requests_entity_id ON change_requests (entity_id);

CREATE INDEX ix_change_requests_status ON change_requests (status);

CREATE INDEX ix_change_requests_entity_type ON change_requests (entity_type);

CREATE TABLE field_revisions (
	id BIGSERIAL NOT NULL, 
	entity_type VARCHAR(60) NOT NULL, 
	entity_id VARCHAR(36) NOT NULL, 
	field_path VARCHAR(120) NOT NULL, 
	revision INTEGER NOT NULL, 
	value_json JSON, 
	actor VARCHAR(160) NOT NULL, 
	changed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX idx_field_revision_lookup ON field_revisions (entity_type, entity_id, field_path, revision);

CREATE TABLE audit_log (
	id BIGSERIAL NOT NULL, 
	actor VARCHAR(160) NOT NULL, 
	action VARCHAR(120) NOT NULL, 
	entity_type VARCHAR(60) NOT NULL, 
	entity_id VARCHAR(36) NOT NULL, 
	before_json JSON, 
	after_json JSON, 
	source_ref TEXT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_audit_log_created_at ON audit_log (created_at);

CREATE TABLE schema_meta (
	key VARCHAR(120) NOT NULL, 
	value VARCHAR(240) NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (key)
);

CREATE TABLE contacts (
	id VARCHAR(36) NOT NULL, 
	name VARCHAR(180) NOT NULL, 
	supplier_id VARCHAR(36), 
	client_id VARCHAR(36), 
	role VARCHAR(160) NOT NULL, 
	phone VARCHAR(100) NOT NULL, 
	email VARCHAR(240) NOT NULL, 
	notes TEXT NOT NULL, 
	source_text TEXT NOT NULL, 
	revision INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(supplier_id) REFERENCES suppliers (id) ON DELETE CASCADE, 
	FOREIGN KEY(client_id) REFERENCES clients (id) ON DELETE CASCADE
);

CREATE INDEX ix_contacts_client_id ON contacts (client_id);

CREATE INDEX ix_contacts_name ON contacts (name);

CREATE INDEX ix_contacts_supplier_id ON contacts (supplier_id);

CREATE TABLE venue_spaces (
	id VARCHAR(36) NOT NULL, 
	venue_id VARCHAR(36) NOT NULL, 
	parent_space_id VARCHAR(36), 
	name VARCHAR(240) NOT NULL, 
	space_type VARCHAR(80) NOT NULL, 
	floor_label VARCHAR(100) NOT NULL, 
	details TEXT NOT NULL, 
	verified_status VARCHAR(60) NOT NULL, 
	verified_at TIMESTAMP WITH TIME ZONE, 
	verified_by VARCHAR(160) NOT NULL, 
	revision INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(venue_id) REFERENCES venues (id) ON DELETE CASCADE, 
	FOREIGN KEY(parent_space_id) REFERENCES venue_spaces (id) ON DELETE SET NULL
);

CREATE INDEX ix_venue_spaces_venue_id ON venue_spaces (venue_id);

CREATE TABLE projects (
	id VARCHAR(36) NOT NULL, 
	name VARCHAR(300) NOT NULL, 
	client_id VARCHAR(36), 
	client_snapshot VARCHAR(240) NOT NULL, 
	owner VARCHAR(160) NOT NULL, 
	phase VARCHAR(60) NOT NULL, 
	description TEXT NOT NULL, 
	cover_document_id VARCHAR(36) NOT NULL, 
	revision INTEGER NOT NULL, 
	archived_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(client_id) REFERENCES clients (id) ON DELETE SET NULL
);

CREATE INDEX ix_projects_phase ON projects (phase);

CREATE INDEX ix_projects_client_id ON projects (client_id);

CREATE INDEX ix_projects_name ON projects (name);

CREATE TABLE document_links (
	id VARCHAR(36) NOT NULL, 
	document_id VARCHAR(36) NOT NULL, 
	entity_type VARCHAR(60) NOT NULL, 
	entity_id VARCHAR(36) NOT NULL, 
	link_role VARCHAR(80) NOT NULL, 
	created_by VARCHAR(160) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_document_link UNIQUE (document_id, entity_type, entity_id, link_role), 
	FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE
);

CREATE INDEX ix_document_links_document_id ON document_links (document_id);

CREATE INDEX ix_document_links_entity_id ON document_links (entity_id);

CREATE INDEX ix_document_links_entity_type ON document_links (entity_type);

CREATE TABLE share_links (
	id VARCHAR(36) NOT NULL, 
	document_id VARCHAR(36) NOT NULL, 
	token_hash VARCHAR(64) NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	allow_download BOOLEAN NOT NULL, 
	revoked_at TIMESTAMP WITH TIME ZONE, 
	created_by VARCHAR(160) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE, 
	UNIQUE (token_hash)
);

CREATE INDEX ix_share_links_document_id ON share_links (document_id);

CREATE TABLE venue_equipment (
	id VARCHAR(36) NOT NULL, 
	space_id VARCHAR(36), 
	name VARCHAR(240) NOT NULL, 
	category VARCHAR(120) NOT NULL, 
	ownership VARCHAR(80) NOT NULL, 
	physical_dimensions VARCHAR(240) NOT NULL, 
	resolution VARCHAR(240) NOT NULL, 
	pixel_pitch VARCHAR(120) NOT NULL, 
	loading_notes TEXT NOT NULL, 
	power_audio_notes TEXT NOT NULL, 
	source_text TEXT NOT NULL, 
	verified_status VARCHAR(60) NOT NULL, 
	verified_at TIMESTAMP WITH TIME ZONE, 
	verified_by VARCHAR(160) NOT NULL, 
	revision INTEGER NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(space_id) REFERENCES venue_spaces (id) ON DELETE SET NULL
);

CREATE INDEX ix_venue_equipment_space_id ON venue_equipment (space_id);

CREATE TABLE event_sessions (
	id VARCHAR(36) NOT NULL, 
	project_id VARCHAR(36) NOT NULL, 
	title VARCHAR(300) NOT NULL, 
	starts_at TIMESTAMP WITH TIME ZONE, 
	ends_at TIMESTAMP WITH TIME ZONE, 
	date_mode VARCHAR(40) NOT NULL, 
	window_start TIMESTAMP WITH TIME ZONE, 
	window_end TIMESTAMP WITH TIME ZONE, 
	venue_space_id VARCHAR(36), 
	location_text TEXT NOT NULL, 
	status VARCHAR(60) NOT NULL, 
	cover_document_id VARCHAR(36) NOT NULL, 
	notes TEXT NOT NULL, 
	revision INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE, 
	FOREIGN KEY(venue_space_id) REFERENCES venue_spaces (id) ON DELETE SET NULL
);

CREATE INDEX ix_event_sessions_starts_at ON event_sessions (starts_at);

CREATE INDEX ix_event_sessions_project_id ON event_sessions (project_id);

CREATE INDEX ix_event_sessions_venue_space_id ON event_sessions (venue_space_id);

CREATE TABLE work_packages (
	id VARCHAR(36) NOT NULL, 
	project_id VARCHAR(36) NOT NULL, 
	supplier_id VARCHAR(36), 
	name VARCHAR(240) NOT NULL, 
	status VARCHAR(60) NOT NULL, 
	description TEXT NOT NULL, 
	contact_snapshot VARCHAR(180) NOT NULL, 
	responsibility TEXT NOT NULL, 
	acceptance_criteria TEXT NOT NULL, 
	planned_entry_at TIMESTAMP WITH TIME ZONE, 
	planned_strike_at TIMESTAMP WITH TIME ZONE, 
	revision INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE, 
	FOREIGN KEY(supplier_id) REFERENCES suppliers (id) ON DELETE SET NULL
);

CREATE INDEX ix_work_packages_supplier_id ON work_packages (supplier_id);

CREATE INDEX ix_work_packages_project_id ON work_packages (project_id);

CREATE TABLE work_package_sessions (
	work_package_id VARCHAR(36) NOT NULL, 
	session_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (work_package_id, session_id), 
	FOREIGN KEY(work_package_id) REFERENCES work_packages (id) ON DELETE CASCADE, 
	FOREIGN KEY(session_id) REFERENCES event_sessions (id) ON DELETE CASCADE
);

CREATE TABLE time_nodes (
	id VARCHAR(36) NOT NULL, 
	project_id VARCHAR(36) NOT NULL, 
	session_id VARCHAR(36), 
	work_package_id VARCHAR(36), 
	node_type VARCHAR(60) NOT NULL, 
	label VARCHAR(240) NOT NULL, 
	planned_start TIMESTAMP WITH TIME ZONE, 
	planned_end TIMESTAMP WITH TIME ZONE, 
	confirmed_start TIMESTAMP WITH TIME ZONE, 
	confirmed_end TIMESTAMP WITH TIME ZONE, 
	actual_start TIMESTAMP WITH TIME ZONE, 
	actual_end TIMESTAMP WITH TIME ZONE, 
	date_status VARCHAR(40) NOT NULL, 
	move_rule VARCHAR(40) NOT NULL, 
	responsible VARCHAR(180) NOT NULL, 
	source_text TEXT NOT NULL, 
	status VARCHAR(60) NOT NULL, 
	notes TEXT NOT NULL, 
	revision INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE, 
	FOREIGN KEY(session_id) REFERENCES event_sessions (id) ON DELETE CASCADE, 
	FOREIGN KEY(work_package_id) REFERENCES work_packages (id) ON DELETE SET NULL
);

CREATE INDEX ix_time_nodes_planned_start ON time_nodes (planned_start);

CREATE INDEX ix_time_nodes_session_id ON time_nodes (session_id);

CREATE INDEX ix_time_nodes_project_id ON time_nodes (project_id);

CREATE INDEX ix_time_nodes_work_package_id ON time_nodes (work_package_id);

CREATE TABLE requirement_items (
	id VARCHAR(36) NOT NULL, 
	project_id VARCHAR(36) NOT NULL, 
	work_package_id VARCHAR(36), 
	name VARCHAR(240) NOT NULL, 
	source_text TEXT NOT NULL, 
	specification TEXT NOT NULL, 
	dimensions VARCHAR(240) NOT NULL, 
	dimension_unit VARCHAR(40) NOT NULL, 
	quantity_text VARCHAR(120) NOT NULL, 
	quantity_unit VARCHAR(60) NOT NULL, 
	intended_use TEXT NOT NULL, 
	location_text TEXT NOT NULL, 
	acceptance_criteria TEXT NOT NULL, 
	delivered_quantity_text VARCHAR(120) NOT NULL, 
	owner VARCHAR(160) NOT NULL, 
	status VARCHAR(60) NOT NULL, 
	revision INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE, 
	FOREIGN KEY(work_package_id) REFERENCES work_packages (id) ON DELETE SET NULL
);

CREATE INDEX ix_requirement_items_work_package_id ON requirement_items (work_package_id);

CREATE INDEX ix_requirement_items_status ON requirement_items (status);

CREATE INDEX ix_requirement_items_project_id ON requirement_items (project_id);

CREATE TABLE tasks (
	id VARCHAR(36) NOT NULL, 
	project_id VARCHAR(36) NOT NULL, 
	work_package_id VARCHAR(36), 
	name VARCHAR(240) NOT NULL, 
	source_text TEXT NOT NULL, 
	status VARCHAR(60) NOT NULL, 
	owner VARCHAR(160) NOT NULL, 
	responsible_party VARCHAR(180) NOT NULL, 
	planned_start TIMESTAMP WITH TIME ZONE, 
	due_at TIMESTAMP WITH TIME ZONE, 
	actual_completed_at TIMESTAMP WITH TIME ZONE, 
	duration_days INTEGER, 
	notes TEXT NOT NULL, 
	evidence_document_id VARCHAR(36) NOT NULL, 
	needs_review BOOLEAN NOT NULL, 
	revision INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE, 
	FOREIGN KEY(work_package_id) REFERENCES work_packages (id) ON DELETE SET NULL
);

CREATE INDEX ix_tasks_due_at ON tasks (due_at);

CREATE INDEX ix_tasks_project_id ON tasks (project_id);

CREATE INDEX ix_tasks_status ON tasks (status);

CREATE INDEX ix_tasks_work_package_id ON tasks (work_package_id);

CREATE TABLE task_requirements (
	task_id VARCHAR(36) NOT NULL, 
	requirement_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (task_id, requirement_id), 
	FOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE, 
	FOREIGN KEY(requirement_id) REFERENCES requirement_items (id) ON DELETE CASCADE
);

CREATE TABLE task_dependencies (
	task_id VARCHAR(36) NOT NULL, 
	depends_on_task_id VARCHAR(36) NOT NULL, 
	description TEXT NOT NULL, 
	dependency_type VARCHAR(40) NOT NULL, 
	PRIMARY KEY (task_id, depends_on_task_id), 
	FOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE, 
	FOREIGN KEY(depends_on_task_id) REFERENCES tasks (id) ON DELETE CASCADE
);
