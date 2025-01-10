import json
import os
import networkx as nx
from pyvis.network import Network

HTML_name= "directed_coauthors_india.html"

##############################################################################
# 1. Load Data from JSON Files
##############################################################################

def load_and_merge_data(file_paths):
    """
    Loads JSON records from multiple files, returns a single list of article records.
    """
    all_data = []
    for fpath in file_paths:
        if not os.path.exists(fpath):
            print(f"WARNING: File not found -> {fpath}")
            continue
        with open(fpath, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                all_data.extend(data)
            except Exception as e:
                print(f"Error reading {fpath}: {e}")
    return all_data


##############################################################################
# 2. Build a PARTIALLY DIRECTED Graph
##############################################################################

def normalize_name(name: str) -> str:
    """
    A simple approach to normalizing names:
      - lowercase
      - strip whitespace
    """
    return name.strip().lower()

def build_partially_directed_graph(articles):
    """
    Creates a DiGraph:
      - editor->author edges are single directed edges
      - co-author relationships are added in BOTH directions, simulating undirected edges.
    """
    G = nx.DiGraph()

    for entry in articles:
        title = entry.get("title", "")
        journal = entry.get("journal", "")
        special_issue = entry.get("special_issue", "")
        issue_id = f"{journal} :: {special_issue}"

        editors_raw = entry.get("editors", [])
        authors_raw = entry.get("authors", [])

        # Normalize names
        editors = [normalize_name(e) for e in editors_raw]
        authors = [normalize_name(a) for a in authors_raw]

        # Update node attributes
        for ed in editors:
            if not G.has_node(ed):
                G.add_node(ed, name=ed, editor_count=0, author_count=0)
            G.nodes[ed]['editor_count'] += 1

        for au in authors:
            if not G.has_node(au):
                G.add_node(au, name=au, editor_count=0, author_count=0)
            G.nodes[au]['author_count'] += 1

        # Directed edges: editor->author
        for ed in editors:
            for au in authors:
                if not G.has_edge(ed, au):
                    G.add_edge(ed, au,
                               relationship='editor_to_author',
                               issues=[issue_id],
                               titles=[title])
                else:
                    # If an edge already exists (maybe co-author),
                    # just append metadata
                    edge_data = G[ed][au]
                    if 'editor_to_author' not in edge_data.get('relationship',''):
                        edge_data['relationship'] += ',editor_to_author'
                    edge_data.setdefault('issues', []).append(issue_id)
                    edge_data.setdefault('titles', []).append(title)

        # Co-author edges: add in BOTH directions
        for i in range(len(authors)):
            for j in range(i+1, len(authors)):
                a1, a2 = authors[i], authors[j]
                # a1 -> a2
                if not G.has_edge(a1, a2):
                    G.add_edge(a1, a2,
                               relationship='co_author',
                               issues=[issue_id],
                               titles=[title])
                else:
                    # update existing edge
                    edge_data = G[a1][a2]
                    if 'co_author' not in edge_data.get('relationship',''):
                        edge_data['relationship'] += ',co_author'
                    edge_data.setdefault('issues', []).append(issue_id)
                    edge_data.setdefault('titles', []).append(title)

                # a2 -> a1 (the "reverse" co-author edge)
                if not G.has_edge(a2, a1):
                    G.add_edge(a2, a1,
                               relationship='co_author',
                               issues=[issue_id],
                               titles=[title])
                else:
                    edge_data = G[a2][a1]
                    if 'co_author' not in edge_data.get('relationship',''):
                        edge_data['relationship'] += ',co_author'
                    edge_data.setdefault('issues', []).append(issue_id)
                    edge_data.setdefault('titles', []).append(title)

    return G


##############################################################################
# 3. Detect Suspicious Overlaps
##############################################################################

def detect_suspicious_patterns(G):
    """
    We'll do:
     - SELF OVERLAP: Person is both editor + author in the same special issue.
     - RECIPROCAL: PersonA edits PersonB's article(s), and PersonB edits PersonA's article(s).
    """
    suspicious_self = []
    suspicious_recip = []

    # We'll store person->issue->roles
    person_issue_roles = {}

    # For each 'editor_to_author' edge, record (editor) has 'editor' in that issue, (author) has 'author'.
    for (u, v, data) in G.edges(data=True):
        if 'editor_to_author' in data.get('relationship',''):
            for iss in data.get('issues', []):
                person_issue_roles.setdefault(u, {}).setdefault(iss, set()).add('editor')
                person_issue_roles.setdefault(v, {}).setdefault(iss, set()).add('author')

    # SELF OVERLAP (same person has 'editor' and 'author' in same issue)
    for person, issue_roles_dict in person_issue_roles.items():
        for issue, roles in issue_roles_dict.items():
            if 'editor' in roles and 'author' in roles:
                suspicious_self.append({
                    'person': person,
                    'issue': issue
                })

    # RECIPROCAL: if we have (u->v) in some issue, and (v->u) in some issue
    # We'll gather all editor->author edges in a dict
    ed_au_map = {}
    for (u, v, data) in G.edges(data=True):
        if 'editor_to_author' in data.get('relationship',''):
            for iss in data.get('issues', []):
                ed_au_map.setdefault((u, v), []).append(iss)

    # If (u->v) and (v->u), that's a reciprocal
    for (u,v), issues_uv in ed_au_map.items():
        if (v,u) in ed_au_map:
            issues_vu = ed_au_map[(v,u)]
            suspicious_recip.append({
                'personA': u,
                'personB': v,
                'issues_A_ed_B_auth': issues_uv,
                'issues_B_ed_A_auth': issues_vu
            })

    return {
        'self_overlap': suspicious_self,
        'reciprocal': suspicious_recip
    }


##############################################################################
# 4. Scoring
##############################################################################

def score_suspicion(suspicions):
    """
    A simple scoring approach:
      +3 for each self-overlap
      +2 for each reciprocal
    """
    score_map = {}

    for s in suspicions['self_overlap']:
        p = s['person']
        score_map[p] = score_map.get(p, 0) + 3

    for r in suspicions['reciprocal']:
        A = r['personA']
        B = r['personB']
        score_map[A] = score_map.get(A, 0) + 2
        score_map[B] = score_map.get(B, 0) + 2

    return score_map


##############################################################################
# 5. Co-Author Cluster Analysis
##############################################################################

def find_coauthor_clusters_directed(G):
    """
    Even though the graph is directed, co-author edges are duplicated.
    We'll convert the co-author subgraph to undirected, then find connected components.
    """
    co_edges = []
    for (u, v, data) in G.edges(data=True):
        if 'co_author' in data.get('relationship',''):
            co_edges.append((u, v))

    co_subgraph = G.edge_subgraph(co_edges).copy()
    # Convert to undirected for cluster analysis
    co_undirected = co_subgraph.to_undirected()
    components = nx.connected_components(co_undirected)

    clusters = []
    for comp in components:
        comp_list = sorted(list(comp))
        if len(comp_list) > 2:  # ignoring trivial pairs
            clusters.append(comp_list)
    return clusters


##############################################################################
# 6. Visualization with PyVis
##############################################################################

def visualize_partially_directed(G, output_html=HTML_name):
    """
    Creates an interactive PyVis network where:
      - We highlight editor->author edges with arrows='to'
      - We highlight co-author edges with arrows='to, from'
        (actually, we store 2 edges in G, so you'll see it in the final rendered result).
    """
    net = Network(height="800px", width="100%", directed=True, bgcolor="#222222", font_color="white")
    net.force_atlas_2based()

    # We'll gather suspicion scores to color nodes
    suspicions = detect_suspicious_patterns(G)
    scores = score_suspicion(suspicions)

    # Add nodes
    for node in G.nodes():
        sc = scores.get(node, 0)
        color = "#00ff00"
        if sc > 0:
            color = "#ff9900" if sc < 5 else "#ff0000"
        net.add_node(node, label=node, title=f"Suspicion: {sc}", color=color)

    # Add edges
    # We'll differentiate the arrow style for co_author vs. editor_to_author
    # but in practice PyVis might show them similarly. We'll add a 'label' or 'title' to clarify.
    for (u, v, data) in G.edges(data=True):
        rel = data.get('relationship','')
        if 'editor_to_author' in rel:
            net.add_edge(u, v,
                         label="editor->author",
                         title=f"{rel}, {data.get('issues','')}",
                         arrows='to')
        elif 'co_author' in rel:
            # We already store co-author in both directions. We'll just mark arrows='to'.
            # The user will see it as effectively "undirected" because there's an edge each way.
            net.add_edge(u, v,
                         label="co_author",
                         title=f"{rel}, {data.get('issues','')}",
                         arrows='to')
        else:
            # If other relationships exist
            net.add_edge(u, v, label=rel, arrows='to')

    net.show(output_html, notebook=False)
    print(f"[Visualization] Saved to: {output_html}")


##############################################################################
# MAIN
##############################################################################

def main():
    # 1. Load data
    '''
        file_paths = [
        "mdpi_articles.json",                # Replace with your actual path(s)
        "mdpi_sustainability_articles.json"
    ]
    '''
    file_paths = [
        "mdpi_sustainability_INDIA_articles.json"
    ]
    articles = load_and_merge_data(file_paths)
    print(f"Loaded {len(articles)} articles.")

    # 2. Build partial DiGraph
    G = build_partially_directed_graph(articles)
    print(f"Constructed DiGraph with {G.number_of_nodes()} nodes, {G.number_of_edges()} edges.")

    # 3. Detect suspicious patterns
    susp = detect_suspicious_patterns(G)
    scores = score_suspicion(susp)

    print("\n--- Self Overlaps (editor=author in same issue) ---")
    for s_item in susp['self_overlap']:
        print(f"   [!] {s_item['person']} in issue: {s_item['issue']}")

    print("\n--- Reciprocal Overlaps (mutual editing) ---")
    for r_item in susp['reciprocal']:
        pa = r_item['personA']
        pb = r_item['personB']
        print(f"   [!] {pa} <--> {pb}")
        print(f"       A_ed_B_auth issues: {r_item['issues_A_ed_B_auth']}")
        print(f"       B_ed_A_auth issues: {r_item['issues_B_ed_A_auth']}\n")

    print("\n--- Suspicion Scores ---")
    for person, sc in sorted(scores.items(), key=lambda x: -x[1]):
        print(f"   {person}: {sc}")

    # 4. Co-author clusters
    clusters = find_coauthor_clusters_directed(G)
    if clusters:
        print("\n--- Potential Co-Author Clusters (undirected approach) ---")
        for c in clusters:
            print(f"   Cluster size {len(c)}: {c}")
    else:
        print("\nNo co-author clusters with more than 2 members found.")
    exit(0)
    # 5. Visualization
    visualize_partially_directed(G, HTML_name)


if __name__ == "__main__":
    main()
