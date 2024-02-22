import streamlit as st
import datetime as datetime
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import plotly.express as px
import os
import utils

# os.environ["TZ"] = "UTC"

root_dir_path = os.path.dirname(os.path.realpath(__file__))

###################
### Page Config ###
###################

st.set_page_config(
    page_title="FPL stats App",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="auto",
)


sidebar_img = utils.get_img_as_base64(
    root_dir_path + "/data/app/wp11906650-fantasy-premier-league-wallpapers.jpg"
)

background_img = utils.get_img_as_base64(
    root_dir_path + "/data/app/wp2598920-white-wallpaper.jpg"
)


#################
### Constants ###
#################

col_name_change_dict = {
    "event": "GW",
    "event_total": "GW Total",
    "player_name": "Manager",
    "entry": "ID",
    "entry_name": "Team Name",
    "rank": "Rank",
    "last_rank": "Last Rank",
    "rank_sort": "Rank Sort",
    "overall_rank": "Overall Rank",
    "total": "Total Points",
    "total_points": "Total Points",
    "points": "Points",
    "value": "Value",
    "bank": "Bank",
    "event_transfers": "Transfers",
    "event_transfers_cost": "Transfer Costs",
    "points_on_bench": "Points on Bench",
    "element_in": "Player_in",
    "element_out": "Player_out",
    "element_in_cost": "Player_in_cost",
    "element_out_cost": "Player_out_cost",
}
heatmap_colourscale = [
    [0, "rgba(61,23,90,255)"],
    [0.35, "rgba(70,160,246,255)"],
    [1, "rgba(72,250,137,255)"],
]


#################
### Functions ###
#################


def inject_custom_css():
    with open(root_dir_path + "/data/app/CSS/styles.txt") as f:
        css_sheet = str(f.read()).format(
            sidebar_img=sidebar_img, background_img=background_img
        )
        st.markdown(
            """<style>{}</style>""".format(css_sheet),
            unsafe_allow_html=True,
        )
    return None


@st.cache_data
def get_league_data(leagueID):
    if not isinstance(leagueID, int):
        leagueID = int(leagueID)
    fpl_league_url_template = (
        "https://fantasy.premierleague.com/api/leagues-classic/{leagueID}/standings/"
    )
    fpl_league_response_json = utils.get_requests_response(
        fpl_league_url_template, leagueID=leagueID
    )
    league_name = fpl_league_response_json["league"]["name"]
    league_df = pd.DataFrame(fpl_league_response_json["standings"]["results"]).rename(
        columns=col_name_change_dict
    )
    return league_name, league_df


@st.cache_data(ttl=3600, show_spinner=False)
def get_all_mngrs_all_gws_df(league_df):
    all_gws_url_template = (
        "https://fantasy.premierleague.com/api/entry/{manager_id}/history/"
    )
    all_gws_df_list = []
    manager_ids = league_df["ID"].values
    managers_completed = st.empty()
    percent_completed = st.empty()
    prog_bar = st.progress(0)
    for i, manager_id in enumerate(manager_ids):
        all_gws_response_json = utils.get_requests_response(
            all_gws_url_template, manager_id=manager_id
        )
        all_gws_df = pd.DataFrame(all_gws_response_json["current"])
        all_gws_df["ID"] = manager_id
        all_gws_df["Team Name"] = league_df.loc[i, "Team Name"]
        all_gws_df["Manager"] = league_df.loc[i, "Manager"]
        all_gws_df_list.append(all_gws_df)
        managers_completed.text(
            "({0}/{1}) Managers completed".format(i, len(manager_ids))
        )
        percent_completed.text("{0:.3f} %".format(100 * ((i + 1) / len(manager_ids))))
        prog_bar.progress((i + 1) / len(manager_ids))
    managers_completed.empty()
    percent_completed.empty()
    prog_bar.empty()
    all_mngrs_all_gws_df = (
        pd.concat(all_gws_df_list)
        .rename(columns=col_name_change_dict)
        .drop(["Rank", "Rank Sort"], axis=1)
    )
    ### Divide by 10
    all_mngrs_all_gws_df["Bank"] = all_mngrs_all_gws_df["Bank"] * 1e5
    all_mngrs_all_gws_df["Value"] = all_mngrs_all_gws_df["Value"] * 1e5
    ### Add league rank as "Rank"
    all_mngrs_all_gws_df["Rank"] = np.nan
    all_mngrs_all_gws_df["Rank"] = all_mngrs_all_gws_df.groupby("GW")[
        "Total Points"
    ].rank(method="min", ascending=False)
    ### Add "Total" columns
    for col in ["Transfers", "Transfer Costs", "Points on Bench"]:
        all_mngrs_all_gws_df[f"Total {col}"] = all_mngrs_all_gws_df.groupby("Manager")[
            col
        ].cumsum()
    ### Add "Form" column
    all_mngrs_all_gws_df["Form"] = all_mngrs_all_gws_df.groupby("Manager")[
        "Points"
    ].transform(lambda s: s.rolling(4, min_periods=1).mean().div(12))
    return all_mngrs_all_gws_df


@st.cache_data
def get_players_df():
    players_df = pd.read_csv(root_dir_path + "/data/app/players_raw.csv").loc[
        :, ["id", "web_name"]
    ]
    return players_df


@st.cache_data(ttl=3600, show_spinner=False)
def get_picks_and_teams_dfs(league_df, players_df, max_gw):
    team_picks_template = (
        "https://fantasy.premierleague.com/api/entry/{manager_id}/event/{gw}/picks/"
    )
    manager_id_name_dict = pd.Series(
        league_df["Manager"].values, index=league_df["ID"]
    ).to_dict()
    id_name_dict = pd.Series(
        players_df["web_name"].values, index=players_df["id"]
    ).to_dict()
    league_teams_df_list = []
    league_picks_dict = {}
    manager_ids = league_df["ID"].values
    managers_completed = st.empty()
    gws_completed = st.empty()
    percent_completed = st.empty()
    prog_bar = st.progress(0)
    for i, manager_id in enumerate(manager_ids):
        league_picks_dict[manager_id] = []
        managers_completed.text(
            "({0}/{1}) Managers completed".format(i, len(manager_ids))
        )
        for j, gw in enumerate(range(1, max_gw + 1)):
            team_selection_response_json = utils.get_requests_response(
                team_picks_template, manager_id=manager_id, gw=gw
            )
            picks_df = pd.DataFrame(team_selection_response_json["picks"])
            picks_df["element"] = picks_df["element"].map(id_name_dict)
            picks_df["manager_id"] = manager_id
            picks_df["gw"] = gw
            picks_df["status"] = np.where(
                (picks_df["is_captain"] == True) & (picks_df["multiplier"] == 2),
                "c",
                np.where(
                    (picks_df["is_captain"] == True) & (picks_df["multiplier"] == 3),
                    "tc",
                    np.where(
                        picks_df["is_vice_captain"] == True,
                        "v",
                        np.where(
                            (picks_df["multiplier"] == 0)
                            | (picks_df["position"].isin([12, 13, 14, 15])),
                            "b",
                            "p",
                        ),
                    ),
                ),
            )
            picks_df["player_pick"] = list(
                (
                    picks_df["element"] + " (" + picks_df["status"].astype(str) + ")"
                ).values
            )
            league_teams_df_list.append(picks_df)
            league_picks_dict[manager_id] += list(
                (picks_df["player_pick"] + picks_df["gw"].astype(str)).values
            )
            gws_completed.text("({0}/{1}) Gameweeks completed".format(j, max_gw))
            percent_completed.text(
                "{0:.3f} %".format(
                    100 * (((i * max_gw) + (j + 1)) / (len(manager_ids) * max_gw))
                )
            )
            prog_bar.progress(((i * max_gw) + (j + 1)) / (len(manager_ids) * max_gw))

    managers_completed.empty()
    gws_completed.empty()
    percent_completed.empty()
    prog_bar.empty()

    league_teams_df = pd.concat(league_teams_df_list).reset_index(drop=True)
    league_teams_df = league_teams_df.replace(
        {"manager_id": manager_id_name_dict}
    ).rename(columns={"manager_id": "Manager"})
    league_picks_df = pd.DataFrame(league_picks_dict).rename(
        columns=manager_id_name_dict
    )
    return league_teams_df, league_picks_df


@st.cache_data(ttl=3600, show_spinner=False)
def get_managers_transfers_df(league_df, players_df):
    transfers_url_template = (
        "https://fantasy.premierleague.com/api/entry/{manager_id}/transfers/"
    )
    manager_id_name_dict = pd.Series(
        league_df["Manager"].values, index=league_df["ID"]
    ).to_dict()
    id_name_dict = pd.Series(
        players_df["web_name"].values, index=players_df["id"]
    ).to_dict()
    transfers_dfs_list = []
    for manager_id in league_df["ID"].values:
        transfers_response_json = utils.get_requests_response(
            transfers_url_template, manager_id=manager_id
        )
        if not transfers_response_json:
            continue
        transfers_df = pd.DataFrame(transfers_response_json)
        transfers_df["element_in"] = transfers_df["element_in"].map(id_name_dict)
        transfers_df["element_in_cost"] = (transfers_df["element_in_cost"] * 1e5).apply(
            lambda n: utils.human_readable(n)
        )
        transfers_df["element_out"] = transfers_df["element_out"].map(id_name_dict)
        transfers_df["element_out_cost"] = (
            transfers_df["element_out_cost"] * 1e5
        ).apply(lambda n: utils.human_readable(n))
        transfers_df["manager_id"] = manager_id
        transfers_df["Manager"] = manager_id_name_dict[manager_id]
        transfers_dfs_list.append(transfers_df)
    all_managers_transfers_df = pd.concat(transfers_dfs_list).rename(
        columns=col_name_change_dict
    )
    return all_managers_transfers_df


##################
### App proper ###
##################


def main():
    inject_custom_css()
    st.title("FPL League Dashboard")
    st.subheader("Input your league ID to view various statistics")

    leagueID = st.number_input(
        "League ID",
        value=None,
        placeholder="Type your league ID here and press ↳ENTER",
        step=1,
    )

    render_elements = False
    if leagueID != None:
        render_elements = True
    else:
        league_df = None
        st.info(
            "How to find you league ID:  \n"
            "👉 Login to your FPL account  \n"
            "👉 Select the 'Leagues & Cups' tab  \n"
            "👉 Select a league  \n"
            "👉 Copy ID from the URL  \n"
        )

    ##############
    ### Render ###
    ##############

    if render_elements:
        league_name, league_df = get_league_data(leagueID)
        with st.spinner(text="(1/2) Collecting and processing season statistics..."):
            all_mngrs_all_gws_df = get_all_mngrs_all_gws_df(league_df)
        players_df = get_players_df()
        max_gw = all_mngrs_all_gws_df["GW"].max()
        with st.spinner(
            text="(2/2) Collecting and processing team selection data, might take a while..."
        ):
            league_teams_df, league_picks_df = get_picks_and_teams_dfs(
                league_df, players_df, max_gw
            )
        # st.dataframe(league_teams_df)
        all_managers_transfers_df = get_managers_transfers_df(league_df, players_df)
        bootstrap_static_url = "https://fantasy.premierleague.com/api/bootstrap-static/"
        with st.sidebar:
            tab_headers = {
                "tab1": "Summary",
                "tab2": "Season Stats.",
                "tab3": "Team Similarity",
                "tab4": "Team Comparison",
                "tab5": "Transfers",
            }
            st.header("Info...")
            with st.expander(tab_headers["tab1"]):
                st.write(
                    "A convenient summary table of league standings for the current season. "
                    "Not too dissimilar to the summary table on the official app/website."
                )
            with st.expander(tab_headers["tab2"]):
                st.write(
                    "A line graph of various statistics for each manager throughout the current season. "
                    "Pick a parameter to plot and adjust the gameweek range. The graph is interactive too!"
                )
            with st.expander(tab_headers["tab3"]):
                st.write(
                    "Check which managers have had similar team selections for a given gameweek. "
                    "Or, select a range of gameweeks to find the average similarity."
                )
            with st.expander(tab_headers["tab4"]):
                st.write(
                    "Compare team selections of two managers for a given gameweek. "
                    "Captained (c), vice-captained (v), and benched (b) players are considered distinct selections."
                )
            with st.expander(tab_headers["tab5"]):
                st.write(
                    "Ever wondered which players your fellow mangers have transfered? and when? "
                    "Then this graph is for you! Zoom in to see multiple tranfers in a single transaction. "
                    "NOTE: Can only see transfers *after* the gameweek deadline. "
                )
        tab1, tab2, tab3, tab4, tab5 = st.tabs(
            [tab_headers[k] for k, v in tab_headers.items()]
        )
        with tab1:
            st.header(f"{league_name}")
            league_df = league_df.merge(
                all_mngrs_all_gws_df.loc[
                    all_mngrs_all_gws_df["GW"] == max_gw, ["Manager", "Form"]
                ],
                how="inner",
                on="Manager",
            )
            st.dataframe(
                league_df[
                    ["Rank", "Manager", "Team Name", "GW Total", "Total Points", "Form"]
                ].style.format({"Form": "{:.2f}"}, thousands=","),
                use_container_width=True,
                hide_index=True,
            )
        with tab2:
            st.header(f"{league_name}")
            with st.container(border=True):
                y_axis_option = st.selectbox(
                    "Pick a Parameter to Plot",
                    sorted(
                        [
                            "Points",
                            "Total Points",
                            "Rank",
                            "Overall Rank",
                            "Bank",
                            "Value",
                            "Form",
                            "Transfers",
                            "Transfer Costs",
                            "Points on Bench",
                            "Total Transfers",
                            "Total Transfer Costs",
                            "Total Points on Bench",
                        ]
                    ),
                    index=3,
                )
                gw_range = st.slider("Select Gameweek Range", 1, max_gw, (1, max_gw))
                fig = px.line(
                    all_mngrs_all_gws_df[
                        all_mngrs_all_gws_df["GW"].between(gw_range[0], gw_range[1])
                    ],
                    x="GW",
                    y=y_axis_option,
                    color="Manager",
                    color_discrete_sequence=px.colors.qualitative.Plotly,
                    markers=True,
                )
                if y_axis_option in ["Rank", "Overall Rank"]:
                    fig.update_yaxes(autorange="reversed")
                st.plotly_chart(fig, theme="streamlit", use_container_width=True)
        with tab3:
            st.header(f"{league_name}")

            with st.container(border=True):
                gw_type = st.radio(
                    "Choose Gameweek Selection Type",
                    ["Single Gameweek", "Multiple Gameweeks"],
                    captions=[
                        "Team similarity of a single GW",
                        "Average similarity over multiple GWs",
                    ],
                    horizontal=True,
                )

                if gw_type == "Single Gameweek":
                    gw_range = st.slider(
                        "Select Gameweek Range", 1, max_gw, max_gw, key="single_gw"
                    )
                    gw_select_indx = list(range((gw_range - 1) * 15, gw_range * 15))
                elif gw_type == "Multiple Gameweeks":
                    gw_range = st.slider(
                        "Select Gameweek Range", 1, max_gw, (1, max_gw), key="multi_gw"
                    )
                    gw_select_indx = list(
                        range((gw_range[0] - 1) * 15, gw_range[1] * 15)
                    )
                else:
                    gw_select_indx = []

                sim_df = utils.jaccard_sim(league_picks_df.iloc[gw_select_indx])
                fig = px.imshow(
                    sim_df,
                    text_auto=False,
                    aspect="auto",
                    color_continuous_scale=heatmap_colourscale,
                    labels=dict(x="Manager 1", y="Manager 2", color="Similarity"),
                )
                st.plotly_chart(fig, theme="streamlit", use_container_width=True)
        with tab4:
            st.header(f"{league_name}")
            with st.container(border=True):
                if gw_type == "Single Gameweek":
                    managers = league_teams_df["Manager"].unique()
                    gw_range = st.slider(
                        "Select Gameweek", 1, max_gw, max_gw, key="single_gw_venn"
                    )
                    col1, col2 = st.columns(2)
                    with col1:
                        manager1 = st.selectbox("Select Manager 1", managers)
                    with col2:
                        manager2 = st.selectbox("Select Manager 2", managers)
                    manager1_set = set(
                        league_teams_df.loc[
                            (league_teams_df["Manager"] == str(manager1))
                            & (league_teams_df["gw"] == int(gw_range)),
                            "player_pick",
                        ]
                    )
                    manager2_set = set(
                        league_teams_df.loc[
                            (league_teams_df["Manager"] == str(manager2))
                            & (league_teams_df["gw"] == int(gw_range)),
                            "player_pick",
                        ]
                    )
                    manager1_players = [
                        s.replace(" (p)", "")
                        for s in manager1_set.difference(manager2_set)
                    ]
                    intersection_players = [
                        s.replace(" (p)", "")
                        for s in manager1_set.intersection(manager2_set)
                    ]
                    manager2_players = [
                        s.replace(" (p)", "")
                        for s in manager2_set.difference(manager1_set)
                    ]
                    words = manager1_players + intersection_players + manager2_players
                    colour1_idx = np.where(managers == manager1)[0][0] % 10
                    colour2_idx = np.where(managers == manager2)[0][0] % 10
                    venn = utils.word_list_venn_diagram(
                        words=words,
                        fontsizes=[10] * len(words),
                        polarities=[-1] * len(manager1_players)
                        + [0] * len(intersection_players)
                        + [1] * len(manager2_players),
                        colour1=px.colors.qualitative.Plotly[colour1_idx],
                        colour2=px.colors.qualitative.Plotly[colour2_idx],
                        scale=1.5,
                    )
                    venn_fig = venn.fig
                    st.pyplot(venn_fig)
        with tab5:
            st.header(f"{league_name}")
            with st.container(border=True):
                bootstrap_static_response = utils.get_requests_response(
                    bootstrap_static_url, kwars={}
                )
                bootstrap_static_df = pd.DataFrame(bootstrap_static_response["events"])
                st.dataframe(bootstrap_static_df)
                st.dataframe(pd.DataFrame(bootstrap_static_response["elements"]).loc[:, ["id", "web_name"]])
                fig = (
                    px.scatter(
                        all_managers_transfers_df,
                        x="time",
                        y="Manager",
                        color="Manager",
                        color_discrete_sequence=px.colors.qualitative.Plotly,
                        hover_name=None,
                        hover_data={
                            "Manager": True,
                            "time": False,
                            "Player_in": True,
                            "Player_in_cost": True,
                            "Player_out": True,
                            "Player_out_cost": True,
                            "GW": False,
                        },
                    )
                    .update_xaxes(
                        rangeslider_visible=True,
                        range=[
                            str(bootstrap_static_df.loc[max_gw - 2, "deadline_time"])[
                                :10
                            ],
                            str(bootstrap_static_df.loc[max_gw, "deadline_time"])[:10],
                        ],
                    )
                    .update_layout(
                        showlegend=True, yaxis_type="category", hovermode="x unified"
                    )
                )
                st.write(datetime.datetime.now().astimezone().tzname())
                for gw in range(1, 39):
                    fig.add_vline(
                        x=datetime.datetime.strptime(
                            bootstrap_static_df.loc[gw - 1, "deadline_time"], "%Y-%m-%dT%H:%M:%SZ"  # type: ignore
                        ).timestamp()
                        * 1000,
                        line_width=1,
                        line_dash="dash",
                        line_color="red",
                        annotation_text=f"Gameweek {gw} Deadline",
                        annotation_position="top",
                    )
                st.plotly_chart(fig, theme="streamlit", use_container_width=True)


if __name__ == "__main__":
    main()
