import streamlit as st
import datetime as datetime
from dataclasses import dataclass
import requests
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import plotly.express as px
import os
import utils

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
standings_url_template = (
    "https://fantasy.premierleague.com/api/leagues-classic/{leagueID}/standings/"
)
history_url_template = (
    "https://fantasy.premierleague.com/api/entry/{manager_id}/history/"
)
picks_url_template = (
    "https://fantasy.premierleague.com/api/entry/{manager_id}/event/{gw}/picks/"
)
transfers_url_template = (
    "https://fantasy.premierleague.com/api/entry/{manager_id}/transfers/"
)
bootstrap_static_url = "https://fantasy.premierleague.com/api/bootstrap-static/"

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


###############
### Classes ###
###############


@dataclass
class LeagueData:
    leagueID: int
    standings_url_template: str
    history_url_template: str
    picks_url_template: str
    transfers_url_template: str
    bootstrap_static_url: str

    def __post_init__(self):
        ### League info
        self.league_name, self.standings_df = self._get_league_name_and_standings()
        self.manager_ids = self.standings_df["ID"].values
        self.manager_id_name_dict = pd.Series(
            self.standings_df["ID"].values, index=self.standings_df["ID"]
        ).to_dict()

        ### Season stats
        with st.spinner(text="(1/2) Collecting and processing season statistics..."):
            self.season_stats_df = self._get_season_stats_df()
        self.max_gw = self.season_stats_df["GW"].max()

        ### Player ID:web_name lookup
        self.player_id_name_dict = self._get_player_id_name_lookup()

    @st.cache_data(ttl=3600, show_spinner=False)
    def _get_season_stats_df(self) -> pd.DataFrame:
        season_stats_list = []
        managers_completed = st.empty()
        percent_completed = st.empty()
        prog_bar = st.progress(0)
        for i, manager_id in enumerate(self.manager_ids):
            history_response_json = self._get_requests_response(
                history_url_template, manager_id=manager_id
            )
            season_stats_per_manager_df = pd.DataFrame(history_response_json["current"])
            season_stats_per_manager_df["ID"] = manager_id
            season_stats_per_manager_df["Team Name"] = self.standings_df.loc[
                i, "Team Name"
            ]
            season_stats_per_manager_df["Manager"] = self.standings_df.loc[i, "Manager"]
            season_stats_list.append(season_stats_per_manager_df)
            managers_completed.text(
                "({0}/{1}) Managers completed".format(i, len(self.manager_ids))
            )
            percent_completed.text(
                "{0:.3f} %".format(100 * ((i + 1) / len(self.manager_ids)))
            )
            prog_bar.progress((i + 1) / len(self.manager_ids))
        managers_completed.empty()
        percent_completed.empty()
        prog_bar.empty()
        season_stats_df = (
            pd.concat(season_stats_list)
            .rename(columns=col_name_change_dict)
            .drop(["Rank", "Rank Sort"], axis=1)
        )
        ### Divide by 10
        season_stats_df["Bank"] = season_stats_df["Bank"] * 1e5
        season_stats_df["Value"] = season_stats_df["Value"] * 1e5
        ### Add league rank as "Rank"
        season_stats_df["Rank"] = np.nan
        season_stats_df["Rank"] = season_stats_df.groupby("GW")["Total Points"].rank(
            method="min", ascending=False
        )
        ### Add "Total" columns
        for col in ["Transfers", "Transfer Costs", "Points on Bench"]:
            season_stats_df[f"Total {col}"] = season_stats_df.groupby("Manager")[
                col
            ].cumsum()
        ### Add "Form" column
        season_stats_df["Form"] = season_stats_df.groupby("Manager")[
            "Points"
        ].transform(lambda s: s.rolling(4, min_periods=1).mean().div(12))
        return season_stats_df

    @st.cache_data
    def _get_league_name_and_standings(self) -> tuple:
        fpl_league_response_json = self._get_requests_response(
            self.standings_url_template, leagueID=self.leagueID
        )
        league_name = fpl_league_response_json["league"]["name"]
        standings_df = pd.DataFrame(
            fpl_league_response_json["standings"]["results"]
        ).rename(columns=col_name_change_dict)
        return league_name, standings_df

    @st.cache_data
    def _get_player_id_name_lookup(self) -> dict:
        bootstrap_static_response = self._get_requests_response(
            bootstrap_static_url, kwars={}
        )
        elements_df = pd.DataFrame(bootstrap_static_response["elements"])
        player_id_name_dict = pd.Series(
            elements_df["web_name"].values, index=elements_df["id"]
        ).to_dict()
        return player_id_name_dict

    def _get_requests_response(self, url_template, **kwargs) -> dict:
        response = requests.get(url_template.format(**kwargs))
        response_json = response.json()
        return response_json


@st.cache_data(ttl=3600, show_spinner=False)
def get_picks_and_teams_dfs(standings_df, player_id_name_dict, max_gw):
    team_picks_template = (
        "https://fantasy.premierleague.com/api/entry/{manager_id}/event/{gw}/picks/"
    )
    manager_id_name_dict = pd.Series(
        standings_df["Manager"].values, index=standings_df["ID"]
    ).to_dict()
    league_teams_df_list = []
    league_picks_dict = {}
    manager_ids = standings_df["ID"].values
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
            picks_df["element"] = picks_df["element"].map(player_id_name_dict)
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
def get_managers_transfers_df(standings_df, player_id_name_dict):
    transfers_url_template = (
        "https://fantasy.premierleague.com/api/entry/{manager_id}/transfers/"
    )
    manager_id_name_dict = pd.Series(
        standings_df["Manager"].values, index=standings_df["ID"]
    ).to_dict()
    transfers_dfs_list = []
    for manager_id in standings_df["ID"].values:
        transfers_response_json = utils.get_requests_response(
            transfers_url_template, manager_id=manager_id
        )
        if not transfers_response_json:
            continue
        transfers_df = pd.DataFrame(transfers_response_json)
        transfers_df["element_in"] = transfers_df["element_in"].map(player_id_name_dict)
        transfers_df["element_in_cost"] = (transfers_df["element_in_cost"] * 1e5).apply(
            lambda n: utils.human_readable(n)
        )
        transfers_df["element_out"] = transfers_df["element_out"].map(
            player_id_name_dict
        )
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
        standings_df = None
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

        ldo = LeagueData(  # league data object
            leagueID=leagueID,  # type: ignore
            standings_url_template=standings_url_template,
            history_url_template=history_url_template,
            picks_url_template=picks_url_template,
            transfers_url_template=transfers_url_template,
            bootstrap_static_url=bootstrap_static_url,
        )

        with st.spinner(
            text="(2/2) Collecting and processing team selection data, might take a while..."
        ):
            league_teams_df, league_picks_df = get_picks_and_teams_dfs(
                ldo.standings_df, ldo.player_id_name_dict, ldo.max_gw
            )
        all_managers_transfers_df = get_managers_transfers_df(
            ldo.standings_df, ldo.player_id_name_dict
        )
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

        """st.write("ldo.standings_df")
        st.dataframe(ldo.standings_df)
        st.write("ldo.season_stats_df")
        st.dataframe(ldo.season_stats_df)
        st.write("league_teams_df")
        st.dataframe(league_teams_df)
        st.write("league_picks_df")
        st.dataframe(league_picks_df)
        st.write("all_managers_transfers_df")
        st.dataframe(all_managers_transfers_df)"""

        with tab1:
            st.header(f"{ldo.league_name}")
            ldo.standings_df = ldo.standings_df.merge(
                ldo.season_stats_df.loc[
                    ldo.season_stats_df["GW"] == ldo.max_gw, ["Manager", "Form"]
                ],
                how="inner",
                on="Manager",
            )
            st.dataframe(
                ldo.standings_df[
                    ["Rank", "Manager", "Team Name", "GW Total", "Total Points", "Form"]
                ].style.format({"Form": "{:.2f}"}, thousands=","),
                use_container_width=True,
                hide_index=True,
            )
        with tab2:
            st.header(f"{ldo.league_name}")
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
                gw_range = st.slider(
                    "Select Gameweek Range", 1, ldo.max_gw, (1, ldo.max_gw)
                )
                fig = px.line(
                    ldo.season_stats_df[
                        ldo.season_stats_df["GW"].between(gw_range[0], gw_range[1])
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
            st.header(f"{ldo.league_name}")

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
                        "Select Gameweek Range",
                        1,
                        ldo.max_gw,
                        ldo.max_gw,
                        key="single_gw",
                    )
                    gw_select_indx = list(range((gw_range - 1) * 15, gw_range * 15))
                elif gw_type == "Multiple Gameweeks":
                    gw_range = st.slider(
                        "Select Gameweek Range",
                        1,
                        ldo.max_gw,
                        (1, ldo.max_gw),
                        key="multi_gw",
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
                    zmax=1.0,
                    zmin=0.0,
                    labels=dict(x="Manager 1", y="Manager 2", color="Similarity"),
                )
                st.plotly_chart(fig, theme="streamlit", use_container_width=True)
        with tab4:
            st.header(f"{ldo.league_name}")
            with st.container(border=True):
                if gw_type == "Single Gameweek":
                    managers = league_teams_df["Manager"].unique()
                    gw_range = st.slider(
                        "Select Gameweek",
                        1,
                        ldo.max_gw,
                        ldo.max_gw,
                        key="single_gw_venn",
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
            st.header(f"{ldo.league_name}")
            with st.container(border=True):
                bootstrap_static_response = utils.get_requests_response(
                    bootstrap_static_url, kwars={}
                )
                bootstrap_static_df = pd.DataFrame(bootstrap_static_response["events"])
                st.dataframe(bootstrap_static_df)
                st.dataframe(
                    pd.DataFrame(bootstrap_static_response["elements"]).loc[
                        :, ["id", "web_name"]
                    ]
                )
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
                            str(
                                bootstrap_static_df.loc[ldo.max_gw - 2, "deadline_time"]
                            )[:10],
                            str(bootstrap_static_df.loc[ldo.max_gw, "deadline_time"])[
                                :10
                            ],
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
