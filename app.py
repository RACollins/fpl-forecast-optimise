import streamlit as st
import numpy as np
import pandas as pd
import requests
import json
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

st.markdown(
    f"""
    <style>
    .stSlider [data-baseweb=slider] {{
    justify-content: center;
    width: 66%;
    left: 11%;
    }}

    [data-testid=stAppViewContainer] {{
        background-image: url("data:image/png;base64,{background_img}");
        background-size: cover;
    }}

    [data-testid="stSidebar"] {{
        background-image: url("data:image/png;base64,{sidebar_img}");
        background-size: cover;
    }}

    [data-testid="stHeader"] {{
        background-image: linear-gradient(90deg, rgba(70,160,248,255), rgba(74,254,141,255));  
    }}
        </style>
        """,
    unsafe_allow_html=True,
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
}
heatmap_colourscale = [
    [0, "rgba(61,23,90,255)"],
    [0.35, "rgba(70,160,246,255)"],
    [1, "rgba(72,250,137,255)"],
]


#################
### Functions ###
#################


@st.cache_data
def get_league_data(leagueID):
    if not isinstance(leagueID, int):
        leagueID = int(leagueID)
    fpl_league_url = (
        f"https://fantasy.premierleague.com/api/leagues-classic/{leagueID}/standings/"
    )
    respose = requests.get(fpl_league_url)
    fpl_league_respose_json = respose.json()
    league_name = fpl_league_respose_json["league"]["name"]
    league_df = pd.DataFrame(fpl_league_respose_json["standings"]["results"]).rename(
        columns=col_name_change_dict
    )
    return league_name, league_df


@st.cache_data(show_spinner=False)
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
        respose = requests.get(all_gws_url_template.format(manager_id=manager_id))
        all_gws_respose_json = respose.json()
        all_gws_df = pd.DataFrame(all_gws_respose_json["current"])
        all_gws_df["ID"] = manager_id
        all_gws_df["Team Name"] = league_df.loc[i, "Team Name"]
        all_gws_df["Manager"] = league_df.loc[i, "Manager"]
        all_gws_df_list.append(all_gws_df)
        managers_completed.text("({0}/{1}) Managers completed".format(i, len(manager_ids)))
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
    max_gw = all_mngrs_all_gws_df["GW"].max()
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


@st.cache_data(show_spinner=False)
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
        managers_completed.text("({0}/{1}) Managers completed".format(i, len(manager_ids)))
        for j, gw in enumerate(range(1, max_gw + 1)):
            respose = requests.get(
                team_picks_template.format(manager_id=manager_id, gw=gw)
            )
            team_selection_respose_json = respose.json()
            picks_df = pd.DataFrame(team_selection_respose_json["picks"])
            picks_df["element"] = picks_df["element"].map(id_name_dict)
            picks_df["manager_id"] = manager_id
            picks_df["gw"] = gw
            picks_df["status"] = np.where(
                picks_df["is_captain"] == True,
                "c",
                np.where(
                    picks_df["is_vice_captain"] == True,
                    "v",
                    np.where(picks_df["multiplier"] == 0, "b", "p"),
                ),
            )
            league_teams_df_list.append(picks_df)
            league_picks_dict[manager_id] += list(
                (
                    picks_df["element"]
                    + "_"
                    + picks_df["status"].astype(str)
                    + "_"
                    + picks_df["gw"].astype(str)
                ).values
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
    league_picks_df = pd.DataFrame(league_picks_dict).rename(
        columns=manager_id_name_dict
    )
    return league_teams_df, league_picks_df


##################
### App proper ###
##################


def main():
    st.title("FPL League Dashboard")
    st.subheader("Input your league ID to view various statistics")

    leagueID = st.number_input(
        "League ID", value=None, placeholder="Type your league ID here and press ↳ENTER", step=1
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
        with st.spinner(text="(2/2) Collecting and processing team selection data, might take a while..."):
            league_teams_df, league_picks_df = get_picks_and_teams_dfs(
                league_df, players_df, max_gw
            )
        with st.sidebar:
            tab_headers = {"tab1": "Summary", "tab2": "Season Stats.", "tab3": "Team Similarity"}
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
        tab1, tab2, tab3 = st.tabs([tab_headers[k] for k, v in tab_headers.items()])
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
            # st.dataframe(league_teams_df)

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
                        "Select Gameweek Range", 1, max_gw, 1, key="single_gw"
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


if __name__ == "__main__":
    main()
